-- Supabase-specific infrastructure only; business schema stays portable PostgreSQL.
-- Keep private. The browser never receives the S3 credentials.
INSERT INTO storage.buckets (id, name, public)
VALUES ('clarora-private', 'clarora-private', false)
ON CONFLICT(id) DO NOTHING;
-- Verify an existing bucket was not previously made public.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM storage.buckets WHERE id='clarora-private' AND public) THEN
    RAISE EXCEPTION 'clarora-private must be private before deployment';
  END IF;
END $$;
