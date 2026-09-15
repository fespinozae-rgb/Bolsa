#!/usr/bin/env python3
"""
Descarga datos diarios de acciones chilenas desde Yahoo Finance (yfinance)
y los agrega a data/history.json para alimentar el dashboard estático.

Corre automáticamente vía GitHub Actions (ver .github/workflows/update-data.yml),
o puedes ejecutarlo manualmente:  python scripts/fetch_data.py
"""

import json
import math
import os
import sys
import urllib.request
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
CRYPTO_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crypto_history.json")
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
            change = ((price - prev_close) / prev_close) * 100 if prev_close and not math.isnan(prev_close) else 0.0
        else:
            change = 0.0

        # Nunca guardar NaN/Infinity: no es JSON válido y rompe el parseo en
        # el navegador (JSON.parse es estricto, a diferencia de Python).
        if math.isnan(price) or math.isinf(price) or math.isnan(change) or math.isinf(change):
            print(f"  [skip] {local_symbol} ({yahoo_ticker}): precio o variación inválidos (NaN/Infinity)")
            return None

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
        change = s["change"]
        if change is None or (isinstance(change, float) and math.isnan(change)):
            continue  # nunca promediar un NaN
        buckets.setdefault(sector, []).append(change)
    return [
        {"name": name, "change": round(sum(vals) / len(vals), 2)}
        for name, vals in buckets.items() if vals
    ]


def fetch_market_indicators():
    """Descarga IPSA, dólar observado (Yahoo) y cobre. Cada uno se salta solo si
    falla, sin afectar a los demás. Además agrega UF, IPC y un conversor de
    monedas (USD, EUR, PEN, ARS) usando mindicador.cl (gratis, sin API key) y
    Yahoo Finance como respaldo/complemento."""
    market = {}
    for key, ticker in MARKET_TICKERS.items():
        result = fetch_one(key, ticker)
        if result:
            market[key] = {"price": result["price"], "change": result["change"]}

    mind = fetch_mindicador()
    if mind:
        if "uf" in mind and "valor" in mind["uf"]:
            market["uf"] = {"price": mind["uf"]["valor"]}
        if "ipc" in mind and "valor" in mind["ipc"]:
            market["ipc"] = {"value": mind["ipc"]["valor"], "period": mind["ipc"].get("fecha", "")[:7]}
        if "euro" in mind and "valor" in mind["euro"]:
            market["eurclp"] = {"price": mind["euro"]["valor"]}

    # Dólar CLP de referencia para armar el conversor: preferimos el ya
    # descargado de Yahoo; si falló, usamos el de mindicador.cl como respaldo.
    usd_clp = market.get("usdclp", {}).get("price")
    if usd_clp is None and mind and "dolar" in mind and "valor" in mind["dolar"]:
        usd_clp = mind["dolar"]["valor"]

    if usd_clp:
        pen = fetch_one("PEN", "PEN=X")
        if pen and pen.get("price"):
            market["penclp"] = {"price": round(usd_clp / pen["price"], 4)}
        ars = fetch_one("ARS", "ARS=X")
        if ars and ars.get("price"):
            market["arsclp"] = {"price": round(usd_clp / ars["price"], 4)}
        if "eurclp" not in market:  # respaldo si mindicador.cl falló
            eur = fetch_one("EUR", "EURUSD=X")
            if eur and eur.get("price"):
                market["eurclp"] = {"price": round(usd_clp * eur["price"], 2)}

    return market


def fetch_mindicador():
    """Descarga UF, IPC, dólar y euro oficiales desde mindicador.cl — API
    pública chilena gratuita, sin necesidad de registro ni API key."""
    try:
        with urllib.request.urlopen("https://mindicador.cl/api", timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [error] mindicador.cl: {exc}")
        return None


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    _save_json_list(HISTORY_PATH, history)


def load_crypto_history():
    if os.path.exists(CRYPTO_HISTORY_PATH):
        with open(CRYPTO_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_crypto_history(entries):
    _save_json_list(CRYPTO_HISTORY_PATH, entries)


def _save_json_list(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Serializamos primero a string (con allow_nan=False) para detectar
    # cualquier NaN/Infinity ANTES de tocar el archivo en disco — así, si algo
    # falla, el archivo existente queda intacto en vez de quedar truncado a
    # medio escribir.
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)


# Criptomonedas a seguir: símbolo -> ticker de Yahoo Finance (par contra USD).
# Reutiliza fetch_one, así que hereda las mismas protecciones (salta si falla
# un ticker puntual, nunca guarda NaN/Infinity).
CRYPTO_TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
}


def fetch_crypto():
    crypto = []
    for local_symbol, ticker in CRYPTO_TICKERS.items():
        result = fetch_one(local_symbol, ticker)
        if result:
            crypto.append(result)
    return crypto


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
    snapshot = {
        "date": date,
        "stocks": stocks,
        "sectors": compute_sectors(stocks),
        "market": market,
    }

    history = load_history()
    history = [h for h in history if h.get("date") != date]  # evita duplicar el día
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])
    save_history(history)

    # Cripto vive en su propio archivo (data/crypto_history.json) porque
    # cotiza todos los días, incluidos fines de semana — a diferencia de las
    # acciones, que solo tienen datos desde que empezamos a trackearlas.
    crypto = fetch_crypto()
    crypto_history = load_crypto_history()
    crypto_history = [c for c in crypto_history if c.get("date") != date]
    if crypto:
        crypto_history.append({"date": date, "crypto": crypto})
    crypto_history.sort(key=lambda c: c["date"])
    save_crypto_history(crypto_history)

    print(f"Listo: {len(stocks)} acciones guardadas para {date} (historial: {len(history)} día(s)). "
          f"{len(crypto)} criptomonedas guardadas (historial cripto: {len(crypto_history)} día(s)).")


if __name__ == "__main__":
    main()
