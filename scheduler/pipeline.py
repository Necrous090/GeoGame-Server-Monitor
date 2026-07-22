"""
Pipeline de ingesta: Cloudflare Radar IQI → PostgreSQL/PostGIS
Orquestado por APScheduler — corre cada 12 horas automáticamente.
"""
import os
import logging
import requests
import psycopg2
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

PAISES = {
    "AG": "Antigua y Barbuda", "AR": "Argentina",   "BB": "Barbados",
    "BO": "Bolivia",           "BR": "Brasil",       "BS": "Bahamas",
    "BZ": "Belice",            "CA": "Canadá",       "CL": "Chile",
    "CO": "Colombia",          "CR": "Costa Rica",   "CU": "Cuba",
    "DM": "Dominica",          "DO": "Rep. Dominicana", "EC": "Ecuador",
    "SV": "El Salvador",       "GD": "Granada",      "GT": "Guatemala",
    "GY": "Guyana",            "HN": "Honduras",     "HT": "Haití",
    "JM": "Jamaica",           "KN": "San Cristóbal","LC": "Santa Lucía",
    "MX": "México",            "NI": "Nicaragua",    "PA": "Panamá",
    "PE": "Perú",              "PY": "Paraguay",     "SR": "Surinam",
    "TT": "Trinidad y Tobago", "US": "Estados Unidos","UY": "Uruguay",
    "VC": "San Vicente",       "VE": "Venezuela",
}

INSERT_SQL = """
    INSERT INTO iqi_measurements (location_code, metric, p25, p50, p75, date_range)
    VALUES (%(location_code)s, %(metric)s, %(p25)s, %(p50)s, %(p75)s, %(date_range)s)
    ON CONFLICT (location_code, captured_at, metric) DO NOTHING
"""


def extract() -> list[dict]:
    """Extrae datos IQI de Cloudflare Radar para los 35 países de América."""
    token = os.environ["CF_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    base = "https://api.cloudflare.com/client/v4"
    rows = []

    for code, nombre in PAISES.items():
        try:
            r = requests.get(
                f"{base}/radar/quality/iqi/summary",
                headers=headers,
                params={"metric": "LATENCY", "location": code, "dateRange": "7d"},
                timeout=30,
            )
            data = r.json()
            if not data.get("success"):
                log.warning("  %s (%s) — API error: %s", nombre, code, data.get("errors"))
                continue
            s = (data.get("result") or {}).get("summary_0")
            if not s:
                log.warning("  %s (%s) — sin datos", nombre, code)
                continue
            rows.append({
                "location_code": code,
                "metric": "LATENCY",
                "p25": float(s["p25"]),
                "p50": float(s["p50"]),
                "p75": float(s["p75"]),
                "date_range": "7d",
            })
            log.info("  ✓ %s (%s) p50=%s ms", nombre, code, s["p50"])
        except Exception as e:
            log.error("  ✗ %s (%s): %s", nombre, code, e)

    log.info("Extract: %d/%d países capturados", len(rows), len(PAISES))
    return rows


def load(rows: list[dict]) -> int:
    """Carga los datos en PostgreSQL/PostGIS."""
    if not rows:
        log.info("Load: nada que insertar.")
        return 0

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "geogame_postgis"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "magedb"),
        user=os.getenv("POSTGRES_USER", "mageuser"),
        password=os.getenv("POSTGRES_PASSWORD", "magepass"),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
                n = cur.rowcount
        log.info("Load: %d filas insertadas en iqi_measurements", n)
        return n
    finally:
        conn.close()


def run_pipeline():
    """Función principal del pipeline ETL."""
    log.info("=" * 50)
    log.info("Pipeline iniciado: %s", datetime.utcnow().isoformat())
    try:
        rows = extract()
        load(rows)
        log.info("Pipeline completado exitosamente.")
    except Exception as e:
        log.error("Pipeline fallido: %s", e)
    log.info("=" * 50)


if __name__ == "__main__":
    # Correr una vez al iniciar el contenedor
    log.info("Iniciando scheduler — primera corrida inmediata...")
    run_pipeline()

    # Programar cada 12 horas
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_pipeline, "interval", hours=12, id="cloudflare_ingestion")
    log.info("Scheduler activo — próxima corrida en 12 horas.")
    scheduler.start()
