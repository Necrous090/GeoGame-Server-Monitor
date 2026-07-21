"""
GeoGame Server Monitor — Loader Cloudflare Radar -> PostGIS (iqi_measurements)
==============================================================================
Python plano, sin Mage. Reusa la llamada YA PROBADA de explore_api.py
(iqi_summary -> result.summary_0.{p25,p50,p75}) y solo agrega el INSERT.

Colócalo en la MISMA carpeta que explore_api.py (importa de ahí).

Corre desde tu máquina (PostGIS en localhost:65432):
    python loader_cloudflare.py

Cada corrida inserta 1 fila por país (6 filas) con metric='LATENCY'.
captured_at usa el default now() de PostGIS: como las 6 filas van en UNA sola
transacción, comparten el mismo timestamp -> cuentan como una "captura".
Corre el loader cada 12h (cron / Task Scheduler) para acumular la serie temporal.

Requisitos (ya los tienes por explore_api): requests, python-dotenv
    pip install psycopg2-binary
"""

import os
import psycopg2

# Reusa la llamada exacta a Cloudflare que ya te funciona
from explore_api import iqi_summary, check_token, PAISES

PG = {
    "user":     os.getenv("POSTGRES_USER", "mageuser"),
    "password": os.getenv("POSTGRES_PASSWORD", "magepass"),
    "host":     "localhost",   # corres desde tu máquina; 'postgres_db' es el host SOLO dentro del compose
    "port":     "65432",       # puerto publicado del container
    "dbname":   os.getenv("POSTGRES_DB", "magedb"),
}

METRIC     = "LATENCY"
DATE_RANGE = "7d"

INSERT_SQL = """
    INSERT INTO iqi_measurements (location_code, metric, p25, p50, p75, date_range)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (location_code, captured_at, metric) DO NOTHING
"""


def _to_num(v):
    """Los percentiles de Cloudflare vienen como strings; la columna es numeric."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def capturar():
    """Llama Cloudflare por cada país y arma las filas a insertar."""
    filas = []
    print(f"Capturando IQI {METRIC} ({DATE_RANGE}) por país:")
    for code, nombre in PAISES.items():
        try:
            d = iqi_summary(code, metric=METRIC, date_range=DATE_RANGE)
            s = d["result"]["summary_0"]
            fila = (code, METRIC, _to_num(s.get("p25")),
                    _to_num(s.get("p50")), _to_num(s.get("p75")), DATE_RANGE)
            filas.append(fila)
            print(f"  {nombre:<14} ({code})  p25={fila[2]}  p50={fila[3]}  p75={fila[4]}")
        except Exception as e:
            print(f"  {nombre:<14} ({code})  sin datos / error: {e}")
    return filas


def guardar(filas):
    """Inserta las filas en una sola transacción (captured_at común a las 6)."""
    if not filas:
        print("Nada que insertar.")
        return 0
    conn = psycopg2.connect(**PG)
    try:
        with conn:                       # commit al salir, rollback si excepción
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, filas)
                n = cur.rowcount
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    check_token()
    filas = capturar()
    n = guardar(filas)
    print(f"\n✓ {n} filas insertadas en iqi_measurements "
          f"(metric={METRIC}, date_range={DATE_RANGE})")
