# GeoGame Server Monitor

Monitoreo geoespacial del estado operativo de la plataforma **LAN** de League of Legends.
Proyecto académico — *Tópicos Especiales II*, Universidad Tecnológica de Panamá.

## Qué hace

Consume el endpoint `lol-status-v4` (`/lol/status/v4/platform-data`) de la región `la1`
cada 12 horas y registra **maintenances** e **incidents** en una base de datos
PostgreSQL/PostGIS. Sobre ese histórico se construye una visualización geoespacial
de los 6 países que componen la región LAN (México, Panamá, Costa Rica, Guatemala,
Colombia, Venezuela).

Es un proyecto **no comercial, single-user**. No recolecta ni procesa datos de jugadores:
solo el estado público de la plataforma.

## Stack

- **Mage AI** — orquestación del pipeline ETL (loader / transformer / exporter) + scheduler 12h
- **PostgreSQL + PostGIS** — almacenamiento con geometría `GEOMETRY(Point, 4326)`
- **Pandas / GeoPandas** — limpieza y análisis geoespacial
- **FastAPI** — API de consulta de estado e incidentes
- **Streamlit** — dashboard con mapa
- **Docker** — entorno reproducible

## API de Riot Games

| Campo | Valor |
|---|---|
| Endpoint | `GET https://la1.api.riotgames.com/lol/status/v4/platform-data` |
| Método | `lol-status-v4` |
| Frecuencia | cada 12 horas |
| Volumen | ~2 requests/día |
| Auth | header `X-Riot-Token` |

## Modelo de datos

- `servers_lan` — un punto por país de LAN, `GEOMETRY(Point, 4326)`
- `incidents` — incidentes con severidad `info` / `warning` / `critical`
- `maintenance` — mantenimientos programados

## Estado

En desarrollo. Etapa 1 (especificación, arquitectura, DDL) completada.