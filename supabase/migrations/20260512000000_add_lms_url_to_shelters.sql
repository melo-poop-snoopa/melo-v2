-- LMS registers its local IP on startup so the admin dashboard
-- can reach it for camera discovery without manual configuration.
ALTER TABLE shelters ADD COLUMN IF NOT EXISTS lms_url TEXT;
