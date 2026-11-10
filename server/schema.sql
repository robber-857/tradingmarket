CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_tokens(hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          plan TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL, limits TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS usage(user_id TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
          period TEXT NOT NULL, bucket TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, response TEXT,
          PRIMARY KEY(user_id,key));
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS saved(user_id TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, payload TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(user_id,id));
        CREATE TABLE IF NOT EXISTS throttle(key TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS throttle_key ON throttle(key,created);
        CREATE TABLE IF NOT EXISTS benefit_reads(user_id TEXT NOT NULL, grant_id TEXT NOT NULL,
          resource TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(user_id,grant_id,resource));
        CREATE TABLE IF NOT EXISTS billing_orders(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          quote TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
          provider_id TEXT, checkout_url TEXT, subscription_id TEXT, customer_id TEXT,
          subscription_status TEXT, cancel_at_end INTEGER NOT NULL DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS billing_provider_order ON billing_orders(provider_id) WHERE provider_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS billing_payments(id TEXT PRIMARY KEY, provider TEXT NOT NULL, reference TEXT NOT NULL,
          order_id TEXT NOT NULL REFERENCES billing_orders(id), amount INTEGER NOT NULL, currency TEXT NOT NULL,
          paid_at REAL NOT NULL, start REAL NOT NULL, end REAL NOT NULL, grant_id TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL DEFAULT 'paid', refunded INTEGER NOT NULL DEFAULT 0,
          UNIQUE(provider,reference));
        CREATE TABLE IF NOT EXISTS billing_refunds(id TEXT PRIMARY KEY, payment_id TEXT NOT NULL UNIQUE REFERENCES billing_payments(id),
          reason TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, provider_id TEXT,
          reviewer TEXT, reviewed_at REAL, note TEXT);
        CREATE TABLE IF NOT EXISTS billing_events(provider TEXT NOT NULL, id TEXT NOT NULL, created REAL NOT NULL,
          PRIMARY KEY(provider,id));
        CREATE TABLE IF NOT EXISTS manual_grants(grant_id TEXT PRIMARY KEY REFERENCES grants(id),
          actor_id TEXT NOT NULL REFERENCES users(id), reason TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_actions(id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id),
          user_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_requests(actor_id TEXT NOT NULL, key TEXT NOT NULL,
          fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(actor_id,key));

CREATE TABLE IF NOT EXISTS auth_pending(hash TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS user_profiles(user_id TEXT PRIMARY KEY REFERENCES users(id), phone TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS oauth_identities(subject TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id));
