from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
import psycopg2
import psycopg2.extras
import psycopg2.pool
import os
from datetime import datetime, date

GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "americas_35.geojson")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mageuser:magepass@geogame_postgis:5432/magedb"
)

app = FastAPI(
    title="GeoGame Server Monitor API",
    description="Monitoreo geoespacial de calidad de red para gaming — Tópicos Especiales II, UTP",
    version="1.0.0",
)

# Pool de conexiones: evita abrir/cerrar una conexión TCP nueva a Postgres
# en cada request. minconn se mantiene siempre listo (sin handshake nuevo).
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=2,
    maxconn=10,
    dsn=DATABASE_URL,
)


def _fetch(sql: str, params=None) -> list[dict]:
    conn = db_pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [
                {k: v.isoformat() if isinstance(v, (datetime, date)) else v
                 for k, v in dict(row).items()}
                for row in cur.fetchall()
            ]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_pool.putconn(conn)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "GeoGame Monitor API"}


@app.get("/geo/americas", tags=["spatial"])
def get_americas_geojson():
    """Polígonos de los 35 países de América (Natural Earth 50m, simplificado)."""
    if not os.path.exists(GEOJSON_PATH):
        raise HTTPException(status_code=404, detail="GeoJSON no disponible")
    return FileResponse(GEOJSON_PATH, media_type="application/geo+json")


@app.get("/locations", tags=["locations"])
def get_locations():
    return _fetch("""
        SELECT
            code    AS country,
            name,
            capital,
            is_focus,
            ST_X(geom) AS longitude,
            ST_Y(geom) AS latitude
        FROM locations
        ORDER BY code
    """)


@app.get("/iqi", tags=["metrics"])
def get_iqi():
    """Última medición disponible por país (snapshot actual)."""
    return _fetch("""
        SELECT DISTINCT ON (i.location_code)
            l.code          AS country,
            l.name,
            l.capital,
            l.subregion,
            l.is_focus,
            ST_X(l.geom)   AS longitude,
            ST_Y(l.geom)   AS latitude,
            i.p25           AS p25_ms,
            i.p50           AS p50_ms,
            i.p75           AS p75_ms,
            i.metric,
            i.date_range,
            i.captured_at
        FROM iqi_measurements i
        JOIN locations l ON l.code = i.location_code
        ORDER BY i.location_code, i.captured_at DESC
    """)


@app.get("/iqi/history", tags=["metrics"])
def get_iqi_history(country: str | None = Query(None, description="Filtrar por código ISO-2 (ej. PA)")):
    """Serie histórica completa (todas las mediciones), para heatmap y tendencias."""
    sql = """
        SELECT
            l.code          AS country,
            l.name,
            l.subregion,
            l.is_focus,
            i.p25           AS p25_ms,
            i.p50           AS p50_ms,
            i.p75           AS p75_ms,
            i.date_range,
            i.captured_at
        FROM iqi_measurements i
        JOIN locations l ON l.code = i.location_code
    """
    params = None
    if country:
        sql += " WHERE l.code = %s"
        params = (country.upper(),)
    sql += " ORDER BY l.code, i.captured_at"
    return _fetch(sql, params)


@app.get("/iqi/summary", tags=["metrics"])
def get_iqi_summary():
    """
    Resumen agregado por país: promedio histórico, última medición y
    cantidad de mediciones — insumo directo del ranking y del choropleth.
    """
    return _fetch("""
        SELECT
            l.code              AS country,
            l.name,
            l.capital,
            l.subregion,
            l.is_focus,
            ST_X(l.geom)        AS longitude,
            ST_Y(l.geom)        AS latitude,
            COUNT(i.id)         AS measurement_count,
            ROUND(AVG(i.p50), 1)   AS avg_p50_ms,
            ROUND(MIN(i.p50), 1)   AS min_p50_ms,
            ROUND(MAX(i.p50), 1)   AS max_p50_ms,
            (ARRAY_AGG(i.p50 ORDER BY i.captured_at DESC))[1] AS latest_p50_ms
        FROM locations l
        LEFT JOIN iqi_measurements i ON i.location_code = l.code
        GROUP BY l.code, l.name, l.capital, l.subregion, l.is_focus, l.geom
        ORDER BY avg_p50_ms DESC NULLS LAST
    """)


@app.get("/iqi/by-subregion", tags=["metrics"])
def get_iqi_by_subregion():
    """Agregado por subregión (Norte/Centro/Caribe/Sur) — para el ranking regional."""
    return _fetch("""
        SELECT
            l.subregion,
            COUNT(DISTINCT l.code)  AS country_count,
            COUNT(i.id)             AS measurement_count,
            ROUND(AVG(i.p50), 1)    AS avg_p50_ms
        FROM locations l
        LEFT JOIN iqi_measurements i ON i.location_code = l.code
        GROUP BY l.subregion
        ORDER BY avg_p50_ms DESC NULLS LAST
    """)


@app.get("/riot", tags=["metrics"])
def get_riot():
    return _fetch("""
        SELECT *
        FROM riot_status
        ORDER BY captured_at DESC
        LIMIT 100
    """)


@app.get("/locations/radius", tags=["spatial"])
def locations_in_radius(
    lat: float = Query(..., description="Latitud del punto de referencia"),
    lon: float = Query(..., description="Longitud del punto de referencia"),
    dist: float = Query(..., gt=0, description="Radio en kilómetros"),
):
    """
    Consulta espacial PostGIS: servidores dentro del radio dado.
    Ejemplo: /locations/radius?lat=9.0&lon=-79.5&dist=2000
    """
    return _fetch(
        """
        SELECT
            l.code          AS country,
            l.name,
            l.capital,
            ST_X(l.geom)   AS longitude,
            ST_Y(l.geom)   AS latitude,
            ROUND(
                (
                    ST_Distance(
                        l.geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) / 1000.0
                )::numeric,
                2
            )::float        AS distance_km
        FROM locations l
        WHERE ST_DWithin(
            l.geom::geography,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
            %s * 1000
        )
        ORDER BY distance_km
        """,
        (lon, lat, lon, lat, dist),
    )