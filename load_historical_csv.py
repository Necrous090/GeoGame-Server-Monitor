"""
load_historical_csv.py
----------------------
Carga historical_iqi.csv a la tabla iqi_measurements en PostGIS.

Uso:
    python load_historical_csv.py
    python load_historical_csv.py --csv otra_ruta.csv

El script omite filas cuyo country_code no exista en la tabla locations,
y evita duplicados via ON CONFLICT (location_code, captured_at, metric).

Si no tienes ese índice único en la DB, el script lo crea automáticamente
antes de insertar.
"""

import os
import csv
import argparse
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "65432")
DB_NAME = os.getenv("DB_NAME", "magedb")
DB_USER = os.getenv("DB_USER", "mageuser")
DB_PASS = os.getenv("DB_PASS", "magepass")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


def ensure_unique_index(conn):
    """Crea índice único para evitar duplicados en cargas repetidas."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_iqi_location_date_metric
            ON iqi_measurements (location_code, captured_at, metric)
        """)
    conn.commit()
    print("✓ Índice único verificado")


def load_csv(path: str, conn) -> tuple[int, int]:
    """
    Inserta filas del CSV en iqi_measurements.
    Retorna (insertadas, omitidas).
    """
    inserted = 0
    skipped  = 0

    # Obtener códigos válidos de locations
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM locations")
        valid_codes = {row[0].strip() for row in cur.fetchall()}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        with conn.cursor() as cur:
            for row in reader:
                code = row["country_code"].strip()

                if code not in valid_codes:
                    print(f"  — {code} no está en locations, omitiendo")
                    skipped += 1
                    continue

                if not row.get("p50_ms"):
                    skipped += 1
                    continue

                try:
                    cur.execute("""
                        INSERT INTO iqi_measurements
                            (location_code, captured_at, metric, p25, p50, p75, date_range)
                        VALUES (%s, %s::timestamptz, %s, %s, %s, %s, %s)
                        ON CONFLICT (location_code, captured_at, metric) DO NOTHING
                    """, (
                        code,
                        row["date_start"],
                        row["metric"],
                        row["p25_ms"] or None,
                        row["p50_ms"] or None,
                        row["p75_ms"] or None,
                        row["month"],        # "2024-01" como date_range
                    ))
                    if cur.rowcount:
                        inserted += 1
                    else:
                        skipped += 1

                except Exception as e:
                    print(f"  ⚠ Error en {code} {row['month']}: {e}")
                    conn.rollback()
                    skipped += 1
                    continue

        conn.commit()

    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Carga historical_iqi.csv → iqi_measurements")
    parser.add_argument("--csv", default="historical_iqi.csv", help="Ruta al CSV")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"❌ No se encontró {args.csv}")
        return

    print(f"Conectando a {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    conn = get_conn()

    ensure_unique_index(conn)

    print(f"Cargando {args.csv}...")
    inserted, skipped = load_csv(args.csv, conn)

    conn.close()

    print(f"\n✓ Listo")
    print(f"  Insertadas: {inserted}")
    print(f"  Omitidas:   {skipped} (duplicados o sin datos)")


if __name__ == "__main__":
    main()
