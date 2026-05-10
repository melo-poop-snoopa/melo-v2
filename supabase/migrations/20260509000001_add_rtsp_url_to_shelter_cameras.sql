-- Optional RTSP URL override on shelter_cameras.
-- When set, the LMS uses this URL directly and skips ONVIF discovery.
-- Useful for local dev (MediaMTX webcam) and cameras that don't speak ONVIF.
ALTER TABLE shelter_cameras ADD COLUMN IF NOT EXISTS rtsp_url TEXT;
