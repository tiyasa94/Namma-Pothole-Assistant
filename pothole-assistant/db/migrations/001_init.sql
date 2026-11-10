-- ============================================================
-- Bengaluru Pothole Assistant — Initial Database Migration
-- Requires: PostgreSQL 14+ with PostGIS and h3-pg extensions
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- h3-pg: install via https://github.com/zachasme/h3-pg
-- CREATE EXTENSION IF NOT EXISTS h3;   -- uncomment when h3-pg is installed

-- ============================================================
-- Table: users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone            VARCHAR(15)  UNIQUE NOT NULL,
    preferred_lang   VARCHAR(2)   NOT NULL DEFAULT 'en'
                         CHECK (preferred_lang IN ('kn', 'hi', 'en')),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    total_reports    INT          NOT NULL DEFAULT 0,
    reputation_score FLOAT        NOT NULL DEFAULT 1.0
);

-- ============================================================
-- Table: road_segments
-- ============================================================
CREATE TABLE IF NOT EXISTS road_segments (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    osm_way_id          BIGINT      UNIQUE,
    name                TEXT,
    geometry            GEOGRAPHY(LINESTRING, 4326),
    quality_score       FLOAT       NOT NULL DEFAULT 100.0,
    score_updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    pothole_count       INT         NOT NULL DEFAULT 0,
    concentration_peak  FLOAT       NOT NULL DEFAULT 0.0,
    under_maintenance   BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_segment_geometry
    ON road_segments USING GIST(geometry);

-- ============================================================
-- Table: pothole_report
-- ============================================================
CREATE TABLE IF NOT EXISTS pothole_report (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    location         GEOGRAPHY(POINT, 4326) NOT NULL,
    h3_index_r9      VARCHAR(15),
    image_url        TEXT,
    severity         VARCHAR(10)
                         CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    user_severity_hint VARCHAR(10)
                         CHECK (user_severity_hint IN ('low', 'medium', 'high', 'critical')),
    ml_confidence    FLOAT,
    pixel_area_pct   FLOAT,
    status           VARCHAR(20)  NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'verified', 'archived', 'disputed')),
    reported_by      UUID        REFERENCES users(id) ON DELETE SET NULL,
    reported_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    road_segment_id  UUID        REFERENCES road_segments(id) ON DELETE SET NULL,
    source           VARCHAR(20)  NOT NULL DEFAULT 'photo'
                         CHECK (source IN ('photo', 'voice', 'passive_sensor')),
    description      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pothole_location
    ON pothole_report USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_pothole_h3
    ON pothole_report(h3_index_r9);

CREATE INDEX IF NOT EXISTS idx_pothole_status
    ON pothole_report(status);

CREATE INDEX IF NOT EXISTS idx_pothole_reported_at
    ON pothole_report(reported_at DESC);

-- ============================================================
-- Table: maintenance_log
-- ============================================================
CREATE TABLE IF NOT EXISTS maintenance_log (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    road_segment_id  UUID        NOT NULL REFERENCES road_segments(id) ON DELETE CASCADE,
    work_type        VARCHAR(20)  NOT NULL
                         CHECK (work_type IN ('repair', 'utility_dig', 'resurfacing', 'patching')),
    status           VARCHAR(20)  NOT NULL DEFAULT 'planned'
                         CHECK (status IN ('planned', 'in_progress', 'completed')),
    logged_by        UUID        REFERENCES users(id) ON DELETE SET NULL,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    notes            TEXT,
    affected_bbox    GEOGRAPHY(POLYGON, 4326)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_segment
    ON maintenance_log(road_segment_id);

-- ============================================================
-- View: active_hotspots
-- Aggregates H3 cells with ≥ 3 verified reports for dashboard
-- ============================================================
CREATE OR REPLACE VIEW active_hotspots AS
SELECT
    h3_index_r9,
    COUNT(*)                          AS report_count,
    MAX(severity)                     AS worst_severity,
    MIN(reported_at)                  AS first_seen,
    MAX(reported_at)                  AS last_seen,
    AVG(ml_confidence)                AS avg_confidence
FROM pothole_report
WHERE status = 'verified'
  AND h3_index_r9 IS NOT NULL
GROUP BY h3_index_r9
HAVING COUNT(*) >= 3
ORDER BY report_count DESC;

-- ============================================================
-- Function: refresh_segment_score()
-- Called by trigger after INSERT/UPDATE on pothole_report
-- ============================================================
CREATE OR REPLACE FUNCTION refresh_segment_score()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_seg_id    UUID;
    v_count     INT;
BEGIN
    v_seg_id := COALESCE(NEW.road_segment_id, OLD.road_segment_id);
    IF v_seg_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT COUNT(*) INTO v_count
    FROM pothole_report
    WHERE road_segment_id = v_seg_id
      AND status = 'verified';

    UPDATE road_segments
    SET
        pothole_count    = v_count,
        score_updated_at = now()
    WHERE id = v_seg_id;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_refresh_segment_score
AFTER INSERT OR UPDATE OF status ON pothole_report
FOR EACH ROW
EXECUTE FUNCTION refresh_segment_score();

-- ============================================================
-- Seed: one sample road segment (Outer Ring Road, Bengaluru)
-- Useful for smoke-testing the API without real OSM data
-- ============================================================
INSERT INTO road_segments (osm_way_id, name, geometry)
VALUES (
    12345678,
    'Outer Ring Road (Marathahalli section)',
    ST_GeographyFromText(
        'LINESTRING(77.695 12.955, 77.700 12.958, 77.705 12.960)'
    )
)
ON CONFLICT (osm_way_id) DO NOTHING;
