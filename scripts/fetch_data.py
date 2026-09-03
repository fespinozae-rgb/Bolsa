#!/usr/bin/env python3
"""
Descarga datos diarios de acciones chilenas desde Yahoo Finance (yfinance)
y los agrega a data/history.json para alimentar el dashboard estático.

Corre automáticamente vía GitHub Actions (ver .github/workflows/update-data.yml),
o puedes ejecutarlo manualmente:  python scripts/fetch_data.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import yfinance as yf

# ---------------------------------------------------------------------------
# Universo de acciones a seguir: símbolo local -> ticker de Yahoo Finance (.SN)
# Ajusta esta lista libremente. Si un ticker falla (delisted, sin datos, mal
# escrito), el script lo salta y sigue con el resto — nunca revienta por uno.
# Puedes verificar/buscar tickers en https://finance.yahoo.com/lookup
# ---------------------------------------------------------------------------
TICKERS = {
    "AGUAS-A": "AGUAS-A.SN",
    "ANTARCHILE": "ANTARCHILE.SN",
    "BSANTANDER": "BSANTANDER.SN",
    "CAP": "CAP.SN",
    "CCU": "CCU.SN",
    "CENCOMALLS": "CENCOMALLS.SN",
    "CENCOSUD": "CENCOSUD.SN",
    "CHILE": "CHILE.SN",
    "CMPC": "CMPC.SN",
    "COLBUN": "COLBUN.SN",
    "COPEC": "COPEC.SN",
    "ECL": "ECL.SN",
    "ENELAM": "ENELAM.SN",
    "ENELCHILE": "ENELCHILE.SN",
    "ENTEL": "ENTEL.SN",
    "FALABELLA": "FALABELLA.SN",
    "IAM": "IAM.SN",
    "ILC": "ILC.SN",
    "ITAUCL": "ITAUCORP.SN",
    "MALLPLAZA": "MALLPLAZA.SN",
    "PARAUCO": "PARAUCO.SN",
    "QUINENCO": "QUINENCO.SN",
    "RIPLEY": "RIPLEY.SN",
    "SALFACORP": "SALFACORP.SN",
    "SMU": "SMU.SN",
    "SONDA": "SONDA.SN",
    "SQM-B": "SQM-B.SN",
    "VAPORES": "VAPORES.SN",
}

# Sector de cada símbolo, para poder calcular rendimiento por sector nosotros
# mismos (Yahoo no entrega un índice sectorial local listo para usar).
SECTORS = {
    "AGUAS-A": "Servicios Públicos", "ANTARCHILE": "Holdings e Inversiones",
    "BSANTANDER": "Banca y Finanzas", "CAP": "Industria y Materiales",
    "CCU": "Consumo Básico", "CENCOMALLS": "Inmobiliario y Construcción",
    "CENCOSUD": "Retail", "CHILE": "Banca y Finanzas", "CMPC": "Industria y Materiales",
    "COLBUN": "Energía", "COPEC": "Energía", "ECL": "Energía",
    "ENELAM": "Energía", "ENELCHILE": "Energía", "ENTEL": "Telecomunicaciones y Tecnología",
    "FALABELLA": "Retail", "IAM": "Servicios Públicos", "ILC": "Salud",
    "ITAUCL": "Banca y Finanzas", "MALLPLAZA": "Inmobiliario y Construcción",
    "PARAUCO": "Inmobiliario y Construcción", "QUINENCO": "Holdings e Inversiones",
    "RIPLEY": "Retail", "SALFACORP": "Inmobiliario y Construcción", "SMU": "Retail",
    "SONDA": "Telecomunicaciones y Tecnología", "SQM-B": "Industria y Materiales",
    "VAPORES": "Transporte",
}

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")
# Chile continuo cierra 16:00 CLT; usamos hora local del runner si ya viene en CLT,
# si no, ajusta TZ_OFFSET_HOURS según corresponda (CLT = UTC-4, CLST verano = UTC-3).
TZ_OFFSET_HOURS = int(os.environ.get("CHILE_TZ_OFFSET", "-4"))

# Indicadores de contexto de mercado (índice, dólar, cobre) — mismo mecanismo
# de descarga que las acciones, se guardan aparte en snapshot["market"].
MARKET_TICKERS = {
    "ipsa": "^IPSA",     # Índice de Precios Selectivo de Acciones
    "usdclp": "CLP=X",   # Dólar observado (CLP por USD)
    "copper": "HG=F",    # Cobre futuro (USD/lb) — referencia clave para la economía chilena
}


def today_santiago():
    tz = timezone(timedelta(hours=TZ_OFFSET_HOURS))
    return datetime.now(tz).strftime("%Y-%m-%d")


def fetch_one(local_symbol, yahoo_ticker):
    try:
        t = yf.Ticker(yahoo_ticker)
        hist = t.history(period="5d")
        if hist.empty or len(hist) < 1:
            print(f"  [skip] {local_symbol} ({yahoo_ticker}): sin datos")
            return None
        last = hist.iloc[-1]
        price = float(last["Close"])
        volume = int(last["Volume"]) if not hist["Volume"].isna().iloc[-1] else None
        if len(hist) >= 2:
            prev_close = float(hist.iloc[-2]["Close"])
            change = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
        else:
            change = 0.0
        return {
            "symbol": local_symbol,
            "price": round(price, 2),
            "change": round(change, 2),
            "volume": volume,
        }
    except Exception as exc:  # noqa: BLE001 - queremos seguir aunque falle un ticker
        print(f"  [error] {local_symbol} ({yahoo_ticker}): {exc}")
        return None


def compute_sectors(stocks):
    buckets = {}
    for s in stocks:
        sector = SECTORS.get(s["symbol"])
        if not sector:
            continue
        buckets.setdefault(sector, []).append(s["change"])
    return [
        {"name": name, "change": round(sum(vals) / len(vals), 2)}
        for name, vals in buckets.items()
    ]


def fetch_market_indicators():
    """Descarga IPSA, dólar observado y cobre. Cada uno se salta solo si falla,
    sin afectar a los demás ni al resto del script."""
    market = {}
    for key, ticker in MARKET_TICKERS.items():
        result = fetch_one(key, ticker)
        if result:
            market[key] = {"price": result["price"], "change": result["change"]}
    return market


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    print("Descargando datos de Yahoo Finance…")
    stocks = []
    for local_symbol, yahoo_ticker in TICKERS.items():
        result = fetch_one(local_symbol, yahoo_ticker)
        if result:
            stocks.append(result)

    if not stocks:
        print("No se obtuvo ningún dato válido. Abortando sin modificar history.json.")
        sys.exit(1)

    date = today_santiago()
    market = fetch_market_indicators()
    snapshot = {"date": date, "stocks": stocks, "sectors": compute_sectors(stocks), "market": market}

    history = load_history()
    history = [h for h in history if h.get("date") != date]  # evita duplicar el día
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])

    save_history(history)
    print(f"Listo: {len(stocks)} acciones guardadas para {date}. "
          f"Historial total: {len(history)} día(s).")


if __name__ == "__main__":
    main()
