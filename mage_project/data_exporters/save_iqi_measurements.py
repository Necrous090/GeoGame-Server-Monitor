import os
import psycopg2
from mage_ai.data_preparation.decorators import data_exporter, test

INSERT_SQL = """
    INSERT INTO iqi_measurements (location_code, metric, p25, p50, p75, date_range)
    VALUES (%(location_code)s, %(metric)s, %(p25)s, %(p50)s, %(p75)s, %(date_range)s)
    ON CONFLICT (location_code, captured_at, metric) DO NOTHING
"""


@data_exporter
def export_data(rows, *args, **kwargs):
    if not rows:
        print("Nada que insertar.")
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
        print(f"✓ {n} filas insertadas en iqi_measurements")
        return n
    finally:
        conn.close()


@test
def test_output(output, *args):
    assert output is not None, "El exporter no devolvió nada"
