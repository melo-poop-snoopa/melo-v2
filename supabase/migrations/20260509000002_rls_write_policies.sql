-- ── RLS write policies for shelter admins ────────────────────────────────────
-- Shelter admins store their shelter_id in Supabase user_metadata.
-- RLS reads it from the JWT: auth.jwt() -> 'user_metadata' ->> 'shelter_id'

-- Shelters: admin can update their own shelter
CREATE POLICY "Shelter admin can update own shelter"
  ON shelters FOR UPDATE
  USING (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = id::text
  )
  WITH CHECK (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = id::text
  );

-- Cats: admin can manage cats belonging to their shelter
CREATE POLICY "Shelter admin can insert own cats"
  ON cats FOR INSERT
  WITH CHECK (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  );

CREATE POLICY "Shelter admin can update own cats"
  ON cats FOR UPDATE
  USING (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  )
  WITH CHECK (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  );

CREATE POLICY "Shelter admin can delete own cats"
  ON cats FOR DELETE
  USING (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  );

-- Streams: rename only — service_role owns status/heartbeat
CREATE POLICY "Shelter admin can rename own streams"
  ON streams FOR UPDATE
  USING (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  )
  WITH CHECK (
    (auth.jwt() -> 'user_metadata' ->> 'shelter_id') = shelter_id::text
  );

-- ── Supabase Storage buckets ──────────────────────────────────────────────────
-- Create buckets for shelter logos and cat photos (public read).
-- Run once; idempotent via DO block.
DO $$
BEGIN
  INSERT INTO storage.buckets (id, name, public)
  VALUES ('shelter-assets', 'shelter-assets', true)
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO storage.buckets (id, name, public)
  VALUES ('cat-photos', 'cat-photos', true)
  ON CONFLICT (id) DO NOTHING;
END $$;

-- Storage RLS: shelter admin can upload to their own folder
CREATE POLICY "Shelter admin can upload logos"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'shelter-assets'
    AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'shelter_id')
  );

CREATE POLICY "Shelter admin can upload cat photos"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'cat-photos'
    AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'shelter_id')
  );

CREATE POLICY "Public can read shelter assets"
  ON storage.objects FOR SELECT
  USING (bucket_id IN ('shelter-assets', 'cat-photos'));
