-- Run AFTER configuring Vault secrets clarora_base_url and clarora_cron_secret
-- and enabling pg_cron + pg_net in the Supabase dashboard.
-- Do not place real secrets directly in this file or in cron job command text.
-- No paid Vercel cron frequency is required: Supabase invokes the HTTP endpoint.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM vault.decrypted_secrets WHERE name='clarora_base_url')
     OR NOT EXISTS (SELECT 1 FROM vault.decrypted_secrets WHERE name='clarora_cron_secret') THEN
    RAISE EXCEPTION 'Configure Clarora Vault secrets first';
  END IF;
END $$;

SELECT cron.schedule('clarora-news', '*/30 * * * *', $$
  SELECT net.http_get(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_base_url') || '/api/cron/news',
    headers := jsonb_build_object('Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_cron_secret')),
    timeout_milliseconds := 300000
  );
$$);
SELECT cron.schedule('clarora-brief', '5 * * * *', $$
  SELECT net.http_get(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_base_url') || '/api/cron/brief',
    headers := jsonb_build_object('Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_cron_secret')),
    timeout_milliseconds := 300000
  );
$$);
SELECT cron.schedule('clarora-forecasts', '20 * * * *', $$
  SELECT net.http_get(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_base_url') || '/api/cron/forecasts',
    headers := jsonb_build_object('Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_cron_secret')),
    timeout_milliseconds := 300000
  );
$$);
