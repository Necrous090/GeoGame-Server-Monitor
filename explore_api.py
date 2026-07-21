"""
GeoGame Server Monitor — Cliente de Cloudflare Radar IQI.
Función compartida por loader_cloudflare.py y fetch_historical_iqi.py.

Uso como smoke test:
    python explore_api.py

Requiere CF_TOKEN en .env (permiso Radar:Read).
"""

import os
import json
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

CF_TOKEN = os.getenv("CF_TOKEN")
BASE_URL = "https://api.cloudflare.com/client/v4/radar/quality/iqi/summary"

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
        print("❌ CF_TOKEN no encontrado en .env")
        sys.exit(1)


def iqi_summary(code: str, metric: str = "LATENCY", date_range: str | None = "7d",
                date_start: str | None = None, date_end: str | None = None) -> dict:
    """
    Llama al endpoint IQI summary de Cloudflare Radar para UN país.

    IMPORTANTE: el parámetro de filtro por país es 'location' (sin '[]').
    Enviar 'location[]' como nombre literal del parámetro hace que Cloudflare
    ignore el filtro y devuelva el agregado global — todos los países salen
    con el mismo valor, que es el bug que tenía fetch_historical_iqi.py.

    Se puede filtrar por ventana relativa (date_range, ej. '7d') o por
    rango absoluto (date_start/date_end, ISO 8601). Si se pasan ambos,
    domina el rango absoluto.
    """
    params = {
        "location": code,
        "metric": metric,
    }
    if date_start and date_end:
        params["dateStart"] = date_start
        params["dateEnd"] = date_end
    else:
        params["dateRange"] = date_range

    r = requests.get(
        BASE_URL,
        headers={"Authorization": f"Bearer {CF_TOKEN}"},
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    if not data.get("success"):
        raise RuntimeError(f"Cloudflare API error para {code}: {data.get('errors')}")

    return data


if __name__ == "__main__":
    check_token()
    print("Smoke test — Cloudflare Radar IQI summary\n")
    for code, nombre in PAISES.items():
        try:
            d = iqi_summary(code, metric="LATENCY", date_range="7d")
            s = d["result"]["summary_0"]
            print(f"  {nombre:<14} ({code})  p25={s.get('p25')}  p50={s.get('p50')}  p75={s.get('p75')}")
        except Exception as e:
            print(f"  {nombre:<14} ({code})  ⚠ error: {e}")
        print("\nPayload completo del último país consultado:")
        print(json.dumps(d, indent=2, ensure_ascii=False)[:1000])
