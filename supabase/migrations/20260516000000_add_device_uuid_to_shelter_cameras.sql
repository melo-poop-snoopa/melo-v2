-- Store the ONVIF device UUID so the LMS can re-discover cameras
-- that have changed IP address (e.g. after a DHCP lease renewal).
ALTER TABLE shelter_cameras ADD COLUMN IF NOT EXISTS device_uuid TEXT;
