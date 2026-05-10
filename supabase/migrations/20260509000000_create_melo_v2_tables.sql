-- Melo v2: Cat live streaming platform tables
-- shelters, streams, cats, shelter_cameras

-- ─── Enums ──────────────────────────────────────────────────────────────────

CREATE TYPE shelter_verification_status AS ENUM ('unverified', 'verified');
CREATE TYPE stream_status AS ENUM ('live', 'offline', 'starting');

-- ─── Shelters ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS shelters (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              TEXT NOT NULL,
    slug              TEXT UNIQUE NOT NULL,
    description       TEXT,
    location          TEXT,
    logo_url          TEXT,
    donation_url      TEXT,
    verification      shelter_verification_status NOT NULL DEFAULT 'unverified',
    impact_metrics    JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER shelters_updated_at
    BEFORE UPDATE ON shelters
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ─── Streams ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS streams (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelter_id        UUID NOT NULL REFERENCES shelters(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    hls_url           TEXT,
    thumbnail_url     TEXT,
    status            stream_status NOT NULL DEFAULT 'offline',
    last_heartbeat    TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER streams_updated_at
    BEFORE UPDATE ON streams
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ─── Cats ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cats (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelter_id        UUID NOT NULL REFERENCES shelters(id) ON DELETE CASCADE,
    stream_id         UUID REFERENCES streams(id) ON DELETE SET NULL,
    name              TEXT NOT NULL,
    age_bracket       TEXT,
    personality       TEXT[],
    photo_url         TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER cats_updated_at
    BEFORE UPDATE ON cats
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ─── Shelter cameras (service_role only) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS shelter_cameras (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelter_id        UUID NOT NULL REFERENCES shelters(id) ON DELETE CASCADE,
    stream_id         UUID REFERENCES streams(id) ON DELETE SET NULL,
    ip_address        TEXT NOT NULL,
    onvif_port        INTEGER NOT NULL DEFAULT 80,
    username          TEXT,
    encrypted_secret  BYTEA,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER shelter_cameras_updated_at
    BEFORE UPDATE ON shelter_cameras
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ─── RLS ────────────────────────────────────────────────────────────────────

ALTER TABLE shelters ENABLE ROW LEVEL SECURITY;
ALTER TABLE streams ENABLE ROW LEVEL SECURITY;
ALTER TABLE cats ENABLE ROW LEVEL SECURITY;
ALTER TABLE shelter_cameras ENABLE ROW LEVEL SECURITY;

-- Public read for shelters, streams, cats (anonymous viewers)
CREATE POLICY "shelters_public_read" ON shelters
    FOR SELECT USING (true);

CREATE POLICY "streams_public_read" ON streams
    FOR SELECT USING (true);

CREATE POLICY "cats_public_read" ON cats
    FOR SELECT USING (true);

-- shelter_cameras: no SELECT policy = denied by default (service_role bypasses RLS)

-- Write policies: permissive stubs for MVP (tighten when auth is integrated)
CREATE POLICY "shelters_service_write" ON shelters
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "streams_service_write" ON streams
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "cats_service_write" ON cats
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "shelter_cameras_service_write" ON shelter_cameras
    FOR ALL USING (true) WITH CHECK (true);

-- ─── Realtime ───────────────────────────────────────────────────────────────

DO $$ BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE streams;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
