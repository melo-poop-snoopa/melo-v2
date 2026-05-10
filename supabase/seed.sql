-- Melo v2 demo seed data
-- Auto-runs on: supabase db reset

INSERT INTO shelters (id, name, slug, description, location, donation_url, verification, impact_metrics)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  'Whisker Haven',
  'whisker-haven',
  'A small no-kill shelter in the Mission dedicated to finding homes for senior cats.',
  'San Francisco, CA',
  'https://gofundme.com/whisker-haven',
  'verified',
  '{"adoptions_2025": 142, "cats_in_care": 38}'::jsonb
) ON CONFLICT (id) DO NOTHING;

INSERT INTO streams (id, shelter_id, name, status)
VALUES (
  '33333333-3333-3333-3333-333333333333',
  '22222222-2222-2222-2222-222222222222',
  'Kitten Room',
  'offline'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO cats (shelter_id, stream_id, name, age_bracket, personality)
VALUES
  ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333',
   'Biscuit', 'senior', ARRAY['Nap Expert', 'Lap Cat']),
  ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333',
   'Mochi', 'kitten', ARRAY['Zoomie King', 'Toy Destroyer']),
  ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333',
   'Soba', 'adult', ARRAY['Window Watcher', 'Chirp Master'])
ON CONFLICT DO NOTHING;

INSERT INTO shelter_cameras (shelter_id, stream_id, ip_address, onvif_port, username)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333',
  '127.0.0.1',
  8080,   -- webcam_onvif_emulator.py default port
  'admin'
  -- rtsp_url left NULL → LMS uses ONVIF (emulator returns rtsp://127.0.0.1:554/webcam)
) ON CONFLICT DO NOTHING;
