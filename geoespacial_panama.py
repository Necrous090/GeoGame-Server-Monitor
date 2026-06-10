"""
GeoGame Server Monitor — Módulo geoespacial (datos reales Cloudflare)
=====================================================================
Adaptación de la guía GeoPandas al schema REAL del proyecto.

Schema real (confirmado en PostGIS):
  - locations(code char(2) PK, name, capital, is_focus bool, geom GEOMETRY(Point,4326))
  - iqi_measurements(location_code FK -> locations.code, p25, p50, p75, captured_at, ...)
  - riot_status(...)  # capa opcional de eventos gaming

Diferencias clave vs. el borrador viejo (servers_lan / incidents):
  - La métrica es LATENCIA IQI (p50), no "severidad de incidentes".
  - Polígonos de país: Natural Earth 50m admin_0, filtrados por ISO_A2 == locations.code.
  - Distancias GEODÉSICAS WGS84 (pyproj.Geod), NO UTM 17N: los 6 países cruzan
    ~6 zonas UTM (MX -> VE), una sola zona daría error grande.

Corre en Python plano contra PostGIS en localhost:65432 (fuera del compose).
  pip install geopandas shapely sqlalchemy psycopg2-binary pyproj matplotlib pandas
"""

import os
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
from pyproj import Geod
import matplotlib.pyplot as plt

plt.rcParams["figure.figsize"] = (13, 10)

# ──────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────
# Desde TU máquina (fuera del compose): host=localhost, port=65432.
# Dentro del network de docker-compose sería host=geogame_postgis, port=5432.
PG = {
    "user":     os.getenv("POSTGRES_USER", "mageuser"),
    "password": os.getenv("POSTGRES_PASSWORD", "magepass"),
    "host":     "localhost",   # corres desde tu máquina; 'postgres_db' es el host SOLO dentro del compose
    "port":     "65432",       # puerto publicado del container
    "db":       os.getenv("POSTGRES_DB", "magedb"),
}
engine = create_engine(
    f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['db']}"
)

# Nombres de columna de iqi_measurements — CONFIRMA con: \d iqi_measurements
COL_FK  = "location_code"   # FK a locations.code
COL_P25 = "p25"
COL_P50 = "p50"
COL_P75 = "p75"
COL_TS  = "captured_at"
METRIC  = "LATENCY"        # iqi_measurements.metric; el schema admite jitter/packet loss

# Polígonos de país (Natural Earth 50m admin_0). Se descarga/cachea local.
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_50m_admin_0_countries.geojson")
NE_CACHE = "ne_50m_admin_0_countries.geojson"

# Los 6 países del alcance (ISO_A2 == locations.code)
PAISES = ["PA", "CR", "GT", "MX", "CO", "VE"]

_GEOD = Geod(ellps="WGS84")


# ══════════════════════════════════════════════════════════════════════════
# PARTE 1 — Carga, CRS y visualización inicial
# ══════════════════════════════════════════════════════════════════════════

def cargar_locations():
    """locations -> GeoDataFrame (las 6 capitales como puntos, EPSG:4326)."""
    locs = gpd.read_postgis("SELECT * FROM locations", engine, geom_col="geom")
    locs = locs.rename_geometry("geometry")   # PostGIS la llama 'geom'; normaliza a 'geometry'
    if locs.crs is None:
        locs = locs.set_crs(epsg=4326)
    locs["code"] = locs["code"].str.strip()  # char(2) puede traer padding
    print(f"locations: {len(locs)} filas | CRS: {locs.crs}")
    return locs


def cargar_paises(path=NE_CACHE):
    """Polígonos de los 6 países. Descarga Natural Earth si no existe local."""
    src = path if os.path.exists(path) else NE_URL
    paises = gpd.read_file(src)
    if not os.path.exists(path):
        paises.to_file(path, driver="GeoJSON")  # cache local para próximas corridas
    paises = paises.to_crs(epsg=4326)
    iso = "ISO_A2" if "ISO_A2" in paises.columns else "ISO_A2_EH"
    paises = paises[paises[iso].isin(PAISES)][[iso, "geometry"]].copy()
    paises = paises.rename(columns={iso: "code"})
    print(f"paises: {len(paises)} polígonos -> {sorted(paises['code'])}")
    return paises


def plot_inicial(locs, paises):
    fig, ax = plt.subplots()
    paises.plot(ax=ax, color="#eef1f5", edgecolor="white", linewidth=0.8)
    # foco (Panamá) en otro color
    foco = locs[locs["is_focus"]]
    resto = locs[~locs["is_focus"]]
    resto.plot(ax=ax, color="#4a90d9", markersize=120, edgecolor="black", zorder=5)
    foco.plot(ax=ax, color="crimson", markersize=220, edgecolor="black", zorder=6)
    for _, r in locs.iterrows():
        ax.annotate(f"{r['name']}\n({r['capital']})",
                    (r["geometry"].x, r["geometry"].y),
                    xytext=(7, 7), textcoords="offset points", fontsize=8)
    ax.set_title("Países monitoreados — GeoGame Server Monitor (foco: Panamá)", fontsize=14)
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout(); plt.show()


# ══════════════════════════════════════════════════════════════════════════
# PARTE 2 — QA espacial: validar que cada capital cae en su país
# (con 6 puntos es control de calidad del seed, no filtro masivo)
# ══════════════════════════════════════════════════════════════════════════

def validar_ubicacion(locs, paises):
    """sjoin punto-en-polígono: el code declarado debe coincidir con el geométrico."""
    chk = gpd.sjoin(locs, paises, how="left", predicate="within", lsuffix="loc", rsuffix="geo")
    chk["match"] = chk["code_loc"] == chk["code_geo"]
    malos = chk[~chk["match"].fillna(False)]
    if len(malos):
        print("⚠ Capitales fuera de su país declarado:")
        print(malos[["code_loc", "code_geo", "name"]])
    else:
        print("✓ Las 6 capitales caen en el país correcto")
    return chk


# ══════════════════════════════════════════════════════════════════════════
# PARTE 3 — Coropleta de LATENCIA (p50 de la captura más reciente por país)
# ══════════════════════════════════════════════════════════════════════════

def latencia_actual():
    """Última captura por país: DISTINCT ON toma la fila más reciente de cada code."""
    sql = f"""
        SELECT DISTINCT ON ({COL_FK})
               {COL_FK} AS code, {COL_P25} AS p25, {COL_P50} AS p50,
               {COL_P75} AS p75, {COL_TS} AS captured_at
        FROM iqi_measurements
        WHERE metric = '{METRIC}'
        ORDER BY {COL_FK}, {COL_TS} DESC
    """
    df = pd.read_sql(sql, engine)
    df["code"] = df["code"].str.strip()
    return df


def coropleta_latencia(paises, locs):
    """Colorea cada país por su p50 más reciente. Sin datos -> aviso y salida."""
    lat = latencia_actual()
    if lat.empty:
        print("⚠ iqi_measurements está vacía: corre el loader de Cloudflare antes "
              "de generar la coropleta de latencia.")
        return None

    analisis = paises.merge(lat, on="code", how="left")
    # nombre legible para etiquetas
    analisis = analisis.merge(locs[["code", "name"]], on="code", how="left")

    fig, ax = plt.subplots()
    analisis.plot(column="p50", ax=ax, cmap="OrRd",
                  linewidth=0.5, edgecolor="grey", legend=True,
                  missing_kwds={"color": "lightgrey", "label": "Sin dato"},
                  legend_kwds={"label": "Latencia IQI p50 (ms)", "orientation": "vertical"})
    for _, r in analisis.iterrows():
        if pd.notna(r["p50"]):
            c = r["geometry"].representative_point()
            ax.annotate(f"{r['name']}\n{r['p50']:.0f} ms", (c.x, c.y),
                        ha="center", fontsize=8, fontweight="bold")
    ax.set_title("Latencia IQI p50 por país — peor = más oscuro", fontsize=14)
    ax.axis("off"); plt.tight_layout(); plt.show()

    print("\nRanking de latencia (p50, menor es mejor):")
    print(analisis[["code", "name", "p25", "p50", "p75"]]
          .sort_values("p50").to_string(index=False))
    return analisis


# ══════════════════════════════════════════════════════════════════════════
# PARTE 4 — Distancias geodésicas + export a GeoPackage
# ══════════════════════════════════════════════════════════════════════════

def matriz_distancias(locs):
    """Matriz de distancias geodésicas (km) entre las 6 capitales. Exacta, sin proyectar."""
    pts = locs[["code", "geometry"]].reset_index(drop=True)
    n = len(pts)
    M = pd.DataFrame(0.0, index=pts["code"], columns=pts["code"])
    for i in range(n):
        for j in range(i + 1, n):
            a, b = pts.geometry[i], pts.geometry[j]
            _, _, d = _GEOD.inv(a.x, a.y, b.x, b.y)   # metros
            km = round(d / 1000, 1)
            M.iloc[i, j] = M.iloc[j, i] = km
    return M


def vecino_mas_cercano(locs, lon, lat, nombre="punto"):
    """Distancia geodésica desde un punto arbitrario a cada capital, ordenado."""
    res = locs[["code", "name", "geometry"]].copy()
    res["dist_km"] = res.geometry.apply(
        lambda g: round(_GEOD.inv(lon, lat, g.x, g.y)[2] / 1000, 1)
    )
    print(f"\nDistancia desde {nombre} ({lon}, {lat}):")
    return res.drop(columns="geometry").sort_values("dist_km")


def cargar_riot():
    """riot_status -> DataFrame tabular (sin geometría; estado por plataforma LAN)."""
    return pd.read_sql(
        "SELECT platform, kind, severity, title, status, captured_at "
        "FROM riot_status ORDER BY captured_at, platform", engine
    )


def exportar_gpkg(locs, analisis, path="geogame_monitor.gpkg"):
    """
    GeoPackage multi-capa en EPSG:4326 (compat Leaflet/Mapbox/QGIS):
      - locations           (puntos)    base
      - paises_latencia     (polígonos) Cloudflare, coropleta p50
      - iqi_latencia_puntos (puntos)    Cloudflare, latencia por país consultable
      - riot_status         (tabla)     Riot, eventos la1/la2 SIN geometría (aspatial)
    """
    # Capas geoespaciales (Cloudflare + base)
    locs.to_crs(epsg=4326).to_file(path, layer="locations", driver="GPKG")
    if analisis is not None:
        analisis.to_crs(epsg=4326).to_file(path, layer="paises_latencia", driver="GPKG")
        # latencia como puntos: cada país con su p25/p50/p75 más reciente
        lat_pts = locs.merge(latencia_actual(), on="code", how="left")
        lat_pts.to_crs(epsg=4326).to_file(path, layer="iqi_latencia_puntos", driver="GPKG")

    # Capa aspatial (Riot): GeoPackage admite tablas sin geometría
    riot = cargar_riot()
    if not riot.empty:
        try:
            import pyogrio
            pyogrio.write_dataframe(riot, path, layer="riot_status")  # tabla aspatial
            print(f"  + riot_status: {len(riot)} eventos (tabla aspatial)")
        except Exception as e:
            # fallback: si pyogrio no está, deja el .gpkg sin la capa Riot pero no falla
            print(f"  ⚠ riot_status no se escribió en el gpkg ({type(e).__name__}); "
                  f"instala pyogrio para incluirla")
    else:
        print("  riot_status vacía: no se añade al gpkg")

    print(f"✓ Exportado a {path}")


# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    locs   = cargar_locations()
    paises = cargar_paises()

    plot_inicial(locs, paises)
    validar_ubicacion(locs, paises)

    analisis = coropleta_latencia(paises, locs)

    print("\nMatriz de distancias entre capitales (km):")
    print(matriz_distancias(locs))

    # ejemplo: vecino más cercano al campus UTP (Vía Centenario)
    print(vecino_mas_cercano(locs, -79.5330, 9.0235, nombre="Campus UTP"))

    exportar_gpkg(locs, analisis)
