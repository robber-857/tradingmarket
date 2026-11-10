-- Independent, idempotent job. Reuses existing Clarora Vault configuration.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM vault.decrypted_secrets WHERE name='clarora_base_url')
     OR NOT EXISTS (SELECT 1 FROM vault.decrypted_secrets WHERE name='clarora_cron_secret') THEN
    RAISE EXCEPTION 'Configure Clarora Vault secrets first';
  END IF;
END $$;
SELECT cron.schedule('clarora-capital', '40 */6 * * *', $$
  SELECT net.http_get(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_base_url') || '/api/cron/capital',
    headers := jsonb_build_object('Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='clarora_cron_secret')),
    timeout_milliseconds := 300000
  );
$$);
