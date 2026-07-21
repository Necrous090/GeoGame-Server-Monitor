# GeoGame Server Monitor

Monitoreo geoespacial de calidad de red para gaming en LATAM, con foco en **Panamá**.
Captura latencia real por país desde Cloudflare Radar, la persiste en PostGIS y la analiza
con GeoPandas (coropletas, distancias geodésicas, export a GeoPackage). Incluye una capa
complementaria de eventos de la plataforma LAN de League of Legends (Riot Status).

> Proyecto de **Tópicos Especiales II — Universidad Tecnológica de Panamá (UTP)**.

---

## Stack

- **Cloudflare Radar API** — fuente principal de datos (latencia IQI por país, free, granularidad nacional).
- **Riot LoL Status v4** — capa complementaria de eventos (incidents / maintenances) de LAN.
- **PostgreSQL + PostGIS** — persistencia geoespacial.
- **GeoPandas / Shapely / pyproj** — análisis geoespacial.
- **Docker Compose** — contenedor de PostGIS.
- *(Roadmap)* Mage AI, FastAPI, Streamlit — orquestación y dashboard.

---

## Decisión de fuentes de datos

Se evaluaron tres fuentes; el diseño quedó así:

| Fuente | Rol | Motivo |
|---|---|---|
| **Cloudflare Radar** | Principal | Free, datos reales con varianza, granularidad por país (incluye Panamá), latencia/jitter/packet loss. |
| **Riot Status** | Complementaria | Estado por plataforma LAN, sin granularidad geográfica. Aporta el hilo de eventos gaming, se cruza por tiempo. |
| **Steam GetServerInfo** | Descartada | No devuelve datacenters ni latencia, solo la hora del servidor. |

**Alcance:** 6 países de LATAM — Panamá (PA, foco), Costa Rica (CR), Guatemala (GT), México (MX), Colombia (CO), Venezuela (VE).

---

## Hallazgo principal

Latencia IQI (percentil p50, ventana 7 días) — datos reales capturados:

| País | p50 (ms) |
|---|---|
| México | ~40 |
| Colombia | ~56 |
| Venezuela | ~66 |
| Costa Rica | ~74 |
| Guatemala | ~74 |
| **Panamá** | **~81** |

Panamá es el **peor** del grupo y México el **mejor** — el ángulo narrativo del proyecto, sostenido con datos reales (no inventados).

---

## Modelo de datos (PostGIS)

- **`locations`** — catálogo de los 6 países. Cada uno un punto (capital como proxy de población).
  `code (char2 PK)`, `name`, `capital`, `is_focus (bool)`, `geom GEOMETRY(Point,4326)`.
- **`iqi_measurements`** — una fila por país por captura; se acumula en el tiempo.
  `location_code (FK)`, `captured_at`, `metric`, `p25`, `p50`, `p75`, `date_range`.
- **`riot_status`** — eventos de la plataforma LAN (la1 / la2). Tabla sin geometría.
  `platform`, `captured_at`, `kind`, `severity`, `title`, `status`.

---

## Requisitos

- Docker + Docker Compose
- Python 3.11+
- Token de Cloudflare Radar (permiso `Radar:Read`)
- API Key de Riot (producto aprobado, no la Development Key que expira cada 24h)

---

## Setup

### 1. Configurar secretos

Copiá `.env.example` a `.env` y completá los tokens:

```
CF_TOKEN=tu_token_cloudflare
RIOT_TOKEN=RGAPI-...
```

> El `.env` está en `.gitignore`. **Nunca lo subas al repo.**

### 2. Levantar PostGIS

```bash
docker compose up -d
```

El `schema.sql` crea las tablas y siembra los 6 países al inicializar el volumen por primera vez.
Verificá:

```bash
docker exec -it geogame_postgis psql -U mageuser -d magedb -c "\dt public.*"
docker exec -it geogame_postgis psql -U mageuser -d magedb -c "SELECT code, name, ST_AsText(geom) FROM locations ORDER BY code;"
```

> Para recargar el schema desde cero: `docker compose down -v && docker compose up -d` (borra el volumen).

### 3. Instalar dependencias de Python

```bash
pip install requests python-dotenv psycopg2-binary geopandas shapely sqlalchemy pyproj matplotlib pandas pyogrio
```

### 4. Capturar datos

```bash
python loader_cloudflare.py    # latencia IQI -> iqi_measurements
python loader_riot.py          # eventos LAN -> riot_status
```

### 5. Análisis geoespacial

```bash
python geoespacial_panama.py
```

Genera los plots (mapa de capitales, coropleta de latencia, matriz de distancias) y exporta `geogame_monitor.gpkg`.

---

## Archivos

```
explore_api.py          Smoke test + exploración del payload de Cloudflare
loader_cloudflare.py    Cloudflare Radar -> iqi_measurements
loader_riot.py          Riot LoL Status v4 -> riot_status
geoespacial_panama.py   Análisis geoespacial + export a GeoPackage
schema.sql              DDL PostGIS + seed de los 6 países
docker-compose.yaml     Contenedor PostGIS (localhost:65432)
.env.example            Plantilla de configuración
```

---

## GeoPackage de salida

`geogame_monitor.gpkg` consolida las tres fuentes en un archivo, abrible en QGIS:

| Capa | Geometría | Fuente |
|---|---|---|
| `locations` | Point | Base (6 países) |
| `paises_latencia` | MultiPolygon | Cloudflare — coropleta p50 |
| `iqi_latencia_puntos` | Point | Cloudflare — latencia por país |
| `riot_status` | — (aspatial) | Riot — eventos la1/la2 |

Cloudflare entra con geometría real (su dato es por país); Riot entra como tabla sin geometría,
porque su dato es por plataforma LAN, no por país. El cruce correcto Riot ↔ latencia es **temporal**
(`captured_at`), no espacial.

---

## Notas

- Los scripts corren **desde tu máquina** contra PostGIS en `localhost:65432`. Dentro del compose, el host sería el nombre del servicio.
- Para una serie temporal, programá los loaders cada 12h (cron / Task Scheduler).
- La distancia entre países usa geodésicas WGS84 (`pyproj.Geod`), no UTM 17N: los 6 países cruzan varias zonas UTM.

## Roadmap

- [ ] Scheduler de capturas cada 12h
- [ ] Dashboard Streamlit (mapa + ranking + overlay temporal de eventos Riot)
- [ ] Pipeline en Mage AI
