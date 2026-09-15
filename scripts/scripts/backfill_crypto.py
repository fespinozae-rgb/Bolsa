#!/usr/bin/env python3
"""
Backfill del histórico de criptomonedas desde el 1 de enero de 2024 hasta hoy,
usando Yahoo Finance. A diferencia de las acciones (que solo tienen datos
desde que empezamos a trackearlas en septiembre 2026), las criptomonedas
cotizan todos los días — incluidos fines de semana — así que este historial
vive en su propio archivo: data/crypto_history.json.

Se ejecuta UNA VEZ (o cuando quieras extender el historial hacia atrás, o
agregar una moneda nueva a CRYPTO_TICKERS en fetch_data.py):

    python scripts/backfill_crypto.py

También puedes dispararlo desde GitHub Actions: pestaña "Actions" →
"Backfill histórico de criptomonedas" → "Run workflow".

No reemplaza los datos que ya guarda fetch_data.py cada día — los combina
sin duplicar.
"""

import json
import math
import os
import sys

import yfinance as yf

# Se importa desde fetch_data.py para no mantener la lista de monedas en dos
# lugares distintos.
from fetch_data import CRYPTO_TICKERS

CRYPTO_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto_history.json")
START_DATE = os.environ.get("CRYPTO_BACKFILL_START", "2024-01-01")


def load_crypto_history():
    if os.path.exists(CRYPTO_HISTORY_PATH):
        with open(CRYPTO_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_crypto_history(entries):
    os.makedirs(os.path.dirname(CRYPTO_HISTORY_PATH), exist_ok=True)
    # allow_nan=False + serializar a string antes de escribir: si algo sale
    # mal, el archivo existente queda intacto en vez de quedar truncado.
    payload = json.dumps(entries, ensure_ascii=False, indent=2, allow_nan=False)
    with open(CRYPTO_HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write(payload)


def fetch_symbol_history(local_symbol, ticker):
    """Descarga el histórico diario completo de una moneda y calcula la
    variación % día a día. Devuelve {fecha: {symbol, price, change, volume}}."""
    result = {}
    try:
        hist = yf.Ticker(ticker).history(start=START_DATE)
    except Exception as exc:  # noqa: BLE001
        print(f"  [error] {local_symbol} ({ticker}): {exc}")
        return result

    if hist.empty:
        print(f"  [skip] {local_symbol}: sin datos históricos")
        return result

    prev_close = None
    for ts, row in hist.iterrows():
        date_str = ts.strftime("%Y-%m-%d")
        price = float(row["Close"])
        volume_raw = row.get("Volume")
        volume = int(volume_raw) if volume_raw is not None and not math.isnan(volume_raw) else None

        if prev_close and not math.isnan(prev_close) and prev_close != 0:
            change = ((price - prev_close) / prev_close) * 100
        else:
            change = 0.0
        prev_close = price

        if math.isnan(price) or math.isinf(price) or math.isnan(change) or math.isinf(change):
            continue  # nunca guardar NaN/Infinity — rompe el JSON en el navegador

        result[date_str] = {
            "symbol": local_symbol,
            "price": round(price, 6 if price < 10 else 2),
            "change": round(change, 2),
            "volume": volume,
        }
    print(f"  [ok] {local_symbol}: {len(result)} días descargados")
    return result


def main():
    print(f"Descargando histórico desde {START_DATE} para {len(CRYPTO_TICKERS)} criptomonedas…")
    by_date = {}  # "YYYY-MM-DD" -> [{symbol, price, change, volume}, ...]

    for local_symbol, ticker in CRYPTO_TICKERS.items():
        per_date = fetch_symbol_history(local_symbol, ticker)
        for date_str, coin_data in per_date.items():
            by_date.setdefault(date_str, []).append(coin_data)

    if not by_date:
        print("No se obtuvo ningún dato. Abortando sin modificar crypto_history.json.")
        sys.exit(1)

    # Combina con lo que ya exista, sin duplicar monedas dentro de un mismo día.
    existing = {e["date"]: e for e in load_crypto_history()}
    for date_str, coins in by_date.items():
        entry = existing.setdefault(date_str, {"date": date_str, "crypto": []})
        existing_symbols = {c["symbol"] for c in entry["crypto"]}
        for coin_data in coins:
            if coin_data["symbol"] not in existing_symbols:
                entry["crypto"].append(coin_data)

    merged = sorted(existing.values(), key=lambda e: e["date"])
    save_crypto_history(merged)
    print(f"Listo: {len(merged)} días guardados en crypto_history.json "
          f"({merged[0]['date']} a {merged[-1]['date']}).")


if __name__ == "__main__":
    main()
