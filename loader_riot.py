"""
GeoGame Server Monitor — Loader Riot LoL Status v4 -> PostGIS (riot_status)
===========================================================================
Capa de eventos gaming: incidents + maintenances de la plataforma LAN.
NO es geoespacial; se cruza por TIEMPO con la serie de latencia
(ej. "¿la latencia subió durante un incident de LAN?").

Token: pon tu API key en el .env como  RIOT_TOKEN=RGAPI-...
       Usa la key del producto aprobado (GEOGAME SERVER MONITOR), no la
       Development Key, que expira cada 24h.

Colócalo en la carpeta del proyecto. Corre desde tu máquina:
    python loader_riot.py

pip install requests python-dotenv psycopg2-binary
"""

import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

RIOT_TOKEN  = os.getenv("RIOT_TOKEN")
PLATAFORMAS = ["la1", "la2"]   # LAN norte (LA1) y sur (LA2/LAS)
LOCALE_PREF = "es_MX"          # idioma preferido para los títulos; fallback al primero

PG = {
    "user":     os.getenv("POSTGRES_USER", "mageuser"),
    "password": os.getenv("POSTGRES_PASSWORD", "magepass"),
    "host":     "localhost",   # corres desde tu máquina, fuera del compose
    "port":     "65432",
    "dbname":   os.getenv("POSTGRES_DB", "magedb"),
}

INSERT_SQL = """
    INSERT INTO riot_status (platform, kind, severity, title, status)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (platform, captured_at, kind, title) DO NOTHING
"""


def status_platform(plat):
    """GET status v4 platform-data de una plataforma (la1 / la2)."""
    url = f"https://{plat}.api.riotgames.com/lol/status/v4/platform-data"
    r = requests.get(url, headers={"X-Riot-Token": RIOT_TOKEN}, timeout=30)
    r.raise_for_status()
    return r.json()


def _title_pref(titles):
    """Toma el título en el locale preferido; si no, el primero disponible."""
    if not titles:
        return None
    for t in titles:
        if t.get("locale") == LOCALE_PREF:
            return t.get("content")
    return titles[0].get("content")


def _extraer(plat, data):
    """Aplana maintenances[] e incidents[] del payload a filas de riot_status."""
    filas = []
    for kind, key in (("maintenance", "maintenances"), ("incident", "incidents")):
        for ev in data.get(key, []):
            filas.append((
                plat,
                kind,
                ev.get("incident_severity"),          # info / warning / critical
                _title_pref(ev.get("titles", [])),
                ev.get("maintenance_status"),         # scheduled / in_progress / complete (None en incidents)
            ))
    return filas


def capturar():
    if not RIOT_TOKEN:
        raise SystemExit("✗ Falta RIOT_TOKEN en el .env (key del producto GEOGAME SERVER MONITOR)")
    filas = []
    print("Capturando status de LoL por plataforma:")
    for plat in PLATAFORMAS:
        try:
            data = status_platform(plat)
            f = _extraer(plat, data)
            filas += f
            print(f"  {plat}: {len(f)} eventos (maintenances + incidents)")
        except requests.RequestException as e:
            print(f"  {plat}: error {e}")
    return filas


def guardar(filas):
    """Inserta en una transacción (captured_at común). 0 eventos es lo normal."""
    if not filas:
        print("0 eventos activos en LAN ahora mismo (lo habitual). Nada que insertar.")
        return 0
    conn = psycopg2.connect(**PG)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, filas)
                n = cur.rowcount
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    filas = capturar()
    n = guardar(filas)
    print(f"\n✓ {n} filas insertadas en riot_status")
