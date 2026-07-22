# GeoGame Server Monitor

Monitoreo geoespacial de calidad de red para gaming en América, con foco en **Panamá**.
Captura latencia real (IQI p25/p50/p75) por país desde Cloudflare Radar, la persiste en
PostGIS y la expone vía API REST y dashboard interactivo.

> Proyecto Semestral — **Tópicos Especiales II · Universidad Tecnológica de Panamá (UTP)**

---

## Stack

| Componente | Tecnología |
|---|---|
| Fuente de datos | Cloudflare Radar API (IQI — latencia por país, 35 naciones de América) |
| Almacenamiento | PostgreSQL 16 + PostGIS 3.4 |
| Orquestación | APScheduler (Python) — cada 12 horas |
| Backend / API | FastAPI + Uvicorn |
| Dashboard | Streamlit + Folium + Plotly |
| Infraestructura | Docker + Docker Compose |

---

## Arquitectura

```
Cloudflare Radar API
        │
        ▼
scheduler/pipeline.py  ──►  PostgreSQL + PostGIS
   (cada 12 horas)                  │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  api/main.py           dashboard/app.py
                  (FastAPI)             (Streamlit + Folium)
                  :8000                 :8501
```

---

## Modelo de datos

```sql
locations         -- 35 países, geometría POINT(lon lat) EPSG:4326
iqi_measurements  -- latencia IQI acumulada (p25/p50/p75) por país y captura
riot_status       -- eventos Riot LoL LAN (opcional, tabla aspatial)
```

---

## Endpoints API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Health check |
| GET | `/locations` | Catálogo de los 35 países con coordenadas |
| GET | `/iqi` | Última medición por país (snapshot actual) |
| GET | `/iqi/history` | Serie histórica completa; acepta `?country=PA` |
| GET | `/iqi/summary` | Promedio histórico + última medición + conteo |
| GET | `/iqi/by-subregion` | Agregado por subregión (Norte/Central/Caribe/Sur) |
| GET | `/iqi/radius` | `?lat=X&lon=Y&dist=km` — consulta espacial PostGIS |
| GET | `/geo/americas` | GeoJSON de polígonos de los 35 países |
| GET | `/riot` | Últimos 100 eventos Riot LAN |

Documentación interactiva: `http://localhost:8000/docs`

---

## Setup

### 1. Configurar variables de entorno

```bash
cp .env.example .env
```

Completar en `.env`:

```
CF_TOKEN=tu_token_cloudflare   # permiso Radar:Read — requerido
RIOT_TOKEN=RGAPI-...           # opcional; solo si quieres poblar riot_status
```

> `.env` está en `.gitignore`. Nunca lo subas al repo.

### 2. Levantar todos los servicios

```bash
docker compose up -d --build
```

Esto levanta 4 servicios:
- `geogame_postgis` — PostGIS en `localhost:65432`
- `geogame_scheduler` — pipeline ETL cada 12h (primera corrida inmediata al arrancar)
- `geogame_api` — FastAPI en `localhost:8000`
- `geogame_dashboard` — Streamlit en `localhost:8501`

El `schema.sql` crea las tablas y siembra los 35 países automáticamente en el primer arranque.

### 3. Verificar

```bash
# Estado de los contenedores
docker compose ps

# Logs del pipeline
docker logs geogame_scheduler -f

# Datos en la DB
docker exec -it geogame_postgis psql -U mageuser -d magedb \
  -c "SELECT COUNT(*) FROM iqi_measurements;"
```

### 4. Acceder

| Servicio | URL |
|---|---|
| Dashboard | http://localhost:8501 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |

---

## Estructura del proyecto

```
GeoGameNew/
├── api/
│   ├── main.py              # FastAPI — endpoints REST y espaciales
│   ├── americas_35.geojson  # Polígonos Natural Earth (GET /geo/americas)
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/
│   ├── app.py               # Streamlit — mapa Folium + ranking + heatmap
│   ├── Dockerfile
│   └── requirements.txt
├── scheduler/
│   ├── pipeline.py          # Extract (Cloudflare) + Load (PostGIS) cada 12h
│   ├── Dockerfile
│   └── requirements.txt
├── schema.sql               # DDL PostGIS + seed 35 países
├── docker-compose.yaml      # Servicio PostGIS
├── docker-compose.override.yml  # Scheduler + API + Dashboard
├── .env.example
└── .gitignore
```

---

## Forzar una corrida manual del pipeline

```bash
docker exec geogame_scheduler python3 -c "from pipeline import run_pipeline; run_pipeline()"
```

---

## Reiniciar la base de datos desde cero

```bash
docker compose down -v && docker compose up -d --build
```
