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
    subregion TEXT,                                -- América del Norte/Central/Caribe/del Sur
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
-- Seed: 35 países soberanos de América (capital como punto).
-- Panamá = foco. Cubre Norte, Centro, Caribe y Sudamérica.
-- geom: ST_MakePoint(LON, LAT) — recuerda el orden X,Y = lon,lat
-- ─────────────────────────────────────────────────────────────
INSERT INTO locations (code, name, capital, subregion, is_focus, geom) VALUES
-- América del Norte
('CA', 'Canada',        'Ottawa',              'América del Norte', FALSE, ST_SetSRID(ST_MakePoint(-75.6972,  45.4215), 4326)),
('US', 'United States', 'Washington D.C.',     'América del Norte', FALSE, ST_SetSRID(ST_MakePoint(-77.0369,  38.9072), 4326)),
('MX', 'México',        'Ciudad de México',    'América del Norte', FALSE, ST_SetSRID(ST_MakePoint(-99.1332,  19.4326), 4326)),
-- América Central
('GT', 'Guatemala',     'Ciudad de Guatemala', 'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-90.5353, 14.6133), 4326)),
('BZ', 'Belize',        'Belmopan',            'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-88.7590, 17.2514), 4326)),
('HN', 'Honduras',      'Tegucigalpa',         'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-87.2068, 14.0818), 4326)),
('SV', 'El Salvador',   'San Salvador',        'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-89.2182, 13.6929), 4326)),
('NI', 'Nicaragua',     'Managua',             'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-86.2514, 12.1364), 4326)),
('CR', 'Costa Rica',    'San José',            'América Central',   FALSE, ST_SetSRID(ST_MakePoint(-84.0833,  9.9333), 4326)),
('PA', 'Panamá',        'Ciudad de Panamá',    'América Central',   TRUE,  ST_SetSRID(ST_MakePoint(-79.5199,  8.9824), 4326)),
-- Caribe
('CU', 'Cuba',                     'La Habana',        'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-82.3666, 23.1136), 4326)),
('JM', 'Jamaica',                  'Kingston',          'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-76.7936, 17.9970), 4326)),
('HT', 'Haití',                    'Puerto Príncipe',   'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-72.3288, 18.5432), 4326)),
('DO', 'República Dominicana',     'Santo Domingo',     'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-69.9312, 18.4861), 4326)),
('TT', 'Trinidad y Tobago',        'Puerto España',     'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-61.5190, 10.6540), 4326)),
('BB', 'Barbados',                 'Bridgetown',        'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-59.6167, 13.0975), 4326)),
('LC', 'Santa Lucía',              'Castries',          'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-60.9875, 14.0101), 4326)),
('VC', 'San Vicente y Granadinas', 'Kingstown',         'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-61.2248, 13.1587), 4326)),
('GD', 'Granada',                  'St. George''s',     'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-61.7518, 12.0526), 4326)),
('AG', 'Antigua y Barbuda',        'St. John''s',       'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-61.8456, 17.1175), 4326)),
('DM', 'Dominica',                 'Roseau',            'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-61.3879, 15.3009), 4326)),
('KN', 'San Cristóbal y Nieves',   'Basseterre',        'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-62.7261, 17.2948), 4326)),
('BS', 'Bahamas',                  'Nassau',            'Caribe', FALSE, ST_SetSRID(ST_MakePoint(-77.3554, 25.0480), 4326)),
-- América del Sur
('CO', 'Colombia',  'Bogotá',       'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-74.0721,  4.7110), 4326)),
('VE', 'Venezuela', 'Caracas',      'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-66.9036, 10.4806), 4326)),
('GY', 'Guyana',    'Georgetown',   'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-58.1551,  6.8013), 4326)),
('SR', 'Surinam',   'Paramaribo',   'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-55.2038,  5.8520), 4326)),
('BR', 'Brasil',    'Brasília',     'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-47.9292, -15.7801), 4326)),
('PE', 'Perú',      'Lima',         'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-77.0428, -12.0464), 4326)),
('EC', 'Ecuador',   'Quito',        'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-78.4678,  -0.1807), 4326)),
('BO', 'Bolivia',   'Sucre',        'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-65.2619, -19.0196), 4326)),
('PY', 'Paraguay',  'Asunción',     'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-57.6470, -25.2867), 4326)),
('CL', 'Chile',     'Santiago',     'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-70.6483, -33.4569), 4326)),
('AR', 'Argentina', 'Buenos Aires', 'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-58.3816, -34.6037), 4326)),
('UY', 'Uruguay',   'Montevideo',   'América del Sur', FALSE, ST_SetSRID(ST_MakePoint(-56.1915, -34.9011), 4326))
ON CONFLICT (code) DO UPDATE SET
    name      = EXCLUDED.name,
    capital   = EXCLUDED.capital,
    subregion = EXCLUDED.subregion,
    is_focus  = EXCLUDED.is_focus,
    geom      = EXCLUDED.geom;
