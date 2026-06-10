"""
GeoGame Server Monitor — Exploración del payload real de Cloudflare Radar.
Objetivo: ver QUÉ devuelve la API antes de diseñar el schema.sql.

Uso:
    python explore_api.py
"""

import os
import json
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

CF_TOKEN = os.getenv("CF_TOKEN")
BASE = "https://api.cloudflare.com/client/v4"
HEADERS = {"Authorization": f"Bearer {CF_TOKEN}"}

# Países LATAM de interés. PA (Panamá) es el foco; el resto es la región de comparación.
PAISES = {
    "PA": "Panamá",
    "CR": "Costa Rica",
    "GT": "Guatemala",
    "MX": "México",
    "CO": "Colombia",
    "VE": "Venezuela",
}


def check_token():
    if not CF_TOKEN:
        sys.exit("✗ Falta CF_TOKEN. Créalo en un archivo .env (ver .env.example)")
    r = requests.get(f"{BASE}/user/tokens/verify", headers=HEADERS, timeout=20)
    data = r.json()
    if not data.get("success"):
        sys.exit(f"✗ Token inválido: {json.dumps(data, indent=2)}")
    print(f"✓ Token activo (status: {data['result'].get('status')})\n")


def iqi_summary(location, metric="LATENCY", date_range="7d"):
    """IQI summary: percentiles de bandwidth / latency / DNS por ubicación."""
    params = {"metric": metric, "location": location, "dateRange": date_range}
    r = requests.get(f"{BASE}/radar/quality/iqi/summary",
                     headers=HEADERS, params=params, timeout=30)
    return r.json()


def speed_summary(location, date_range="7d"):
    """Speed summary: bandwidth, latency, jitter y packetLoss (90 días de speed tests)."""
    params = {"location": location, "dateRange": date_range}
    r = requests.get(f"{BASE}/radar/quality/speed/summary",
                     headers=HEADERS, params=params, timeout=30)
    return r.json()


if __name__ == "__main__":
    check_token()

    # 1) Payload CRUDO de un país, para ver la estructura completa que alimentará el schema
    print("=" * 70)
    print("PAYLOAD CRUDO — IQI summary LATENCY (Panamá)")
    print("=" * 70)
    raw = iqi_summary("PA", metric="LATENCY")
    print(json.dumps(raw, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("PAYLOAD CRUDO — Speed summary (Panamá) [jitter + packetLoss]")
    print("=" * 70)
    raw_speed = speed_summary("PA")
    print(json.dumps(raw_speed, indent=2, ensure_ascii=False))

    # 2) Tabla comparativa de latencia por país (lo que se vuelve filas en PostGIS)
    print("\n" + "=" * 70)
    print("LATENCIA (IQI p50) POR PAÍS — últimos 7 días")
    print("=" * 70)
    for code, nombre in PAISES.items():
        try:
            d = iqi_summary(code, metric="LATENCY")
            s = d["result"]["summary_0"]
            print(f"{nombre:<14} ({code})  p25={s.get('p25')}  p50={s.get('p50')}  p75={s.get('p75')}")
        except (KeyError, requests.RequestException) as e:
            print(f"{nombre:<14} ({code})  sin datos / error: {e}")
