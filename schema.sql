-- GeoGame Server Monitor — Schema PostGIS
-- Basado en el payload REAL de Cloudflare Radar IQI (latencia por país).

CREATE EXTENSION IF NOT EXISTS postgis;

-- ─────────────────────────────────────────────────────────────
-- Catálogo de países monitoreados (puntos fijos)
-- El punto es la capital, proxy de la población/jugadores del país.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS locations (
    code      CHAR(2)               PRIMARY KEY,   -- alpha-2 (PA, CR, ...)
    name      TEXT                  NOT NULL,
    capital   TEXT                  NOT NULL,
    is_focus  BOOLEAN               DEFAULT FALSE, -- Panamá = TRUE
    geom      GEOMETRY(Point, 4326) NOT NULL
);

-- ─────────────────────────────────────────────────────────────
-- Mediciones de latencia (IQI). Una fila por país por captura.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS iqi_measurements (
    id            BIGSERIAL    PRIMARY KEY,
    location_code CHAR(2)      NOT NULL REFERENCES locations(code),
    captured_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    metric        TEXT         NOT NULL DEFAULT 'LATENCY',
    p25           NUMERIC,
    p50           NUMERIC,
    p75           NUMERIC,
    date_range    TEXT         DEFAULT '7d',
    UNIQUE (location_code, captured_at, metric)
);

-- ─────────────────────────────────────────────────────────────
-- (Opcional, capa gaming) eventos de la plataforma Riot LAN.
-- Se llena desde la Riot Status API cuando tengas la Personal key.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS riot_status (
    id          BIGSERIAL   PRIMARY KEY,
    platform    TEXT        NOT NULL DEFAULT 'la1',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind        TEXT,       -- 'incident' | 'maintenance'
    severity    TEXT,       -- info | warning | critical
    title       TEXT,
    status      TEXT,       -- monitoring | resolved | scheduled ...
    UNIQUE (platform, captured_at, kind, title)
);

CREATE INDEX IF NOT EXISTS idx_locations_geom ON locations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_iqi_location   ON iqi_measurements (location_code);
CREATE INDEX IF NOT EXISTS idx_iqi_captured   ON iqi_measurements (captured_at);

-- ─────────────────────────────────────────────────────────────
-- Seed: 6 países LATAM (capital como punto). Panamá = foco.
-- geom: ST_MakePoint(LON, LAT) — recuerda el orden X,Y = lon,lat
-- ─────────────────────────────────────────────────────────────
INSERT INTO locations (code, name, capital, is_focus, geom) VALUES
('PA', 'Panamá',     'Ciudad de Panamá',     TRUE,  ST_SetSRID(ST_MakePoint(-79.5199,  8.9824), 4326)),
('CR', 'Costa Rica', 'San José',             FALSE, ST_SetSRID(ST_MakePoint(-84.0833,  9.9333), 4326)),
('GT', 'Guatemala',  'Ciudad de Guatemala',  FALSE, ST_SetSRID(ST_MakePoint(-90.5133, 14.6133), 4326)),
('MX', 'México',     'Ciudad de México',     FALSE, ST_SetSRID(ST_MakePoint(-99.1332, 19.4326), 4326)),
('CO', 'Colombia',   'Bogotá',               FALSE, ST_SetSRID(ST_MakePoint(-74.0721,  4.7110), 4326)),
('VE', 'Venezuela',  'Caracas',              FALSE, ST_SetSRID(ST_MakePoint(-66.9036, 10.4806), 4326))
ON CONFLICT (code) DO NOTHING;
