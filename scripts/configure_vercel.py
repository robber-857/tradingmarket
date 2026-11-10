"""Upload an explicit server-only allowlist to the linked Vercel project.

Credentials travel on stdin, never command-line arguments or console output.
"""
from pathlib import Path
import subprocess
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'output/vercel-cli/node_modules/@vercel/cli-support/dist/vc.js'
KEYS = '''CLARORA_MODE CLARORA_PUBLIC_URL DATABASE_URL CLARORA_STORAGE_BACKEND
S3_ENDPOINT_URL S3_BUCKET AWS_REGION AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
CRON_SECRET NEWS_BACKGROUND_ENABLED PUBLIC_FORECAST_BACKGROUND_ENABLED
DAILY_BRIEF_ENABLED DAILY_BRIEF_HOUR EMAIL_LOGIN_ENABLED SEC_USER_AGENT
OPENAI_API_KEY OPENAI_MODEL TWELVE_DATA_API_KEY TRADING_ECONOMICS_API_KEY
X_BEARER_TOKEN SMTP_HOST SMTP_PORT SMTP_FROM SMTP_USER SMTP_PASSWORD
CLARORA_ADMIN_EMAILS CLARORA_ADMIN_USER_IDS BILLING_ADMIN_USER_IDS
BILLING_TEST_ENABLED STRIPE_TEST_SECRET_KEY STRIPE_TEST_WEBHOOK_SECRET
STRIPE_TEST_PORTAL_CONFIGURATION PAYPAL_SANDBOX_CLIENT_ID
PAYPAL_SANDBOX_CLIENT_SECRET PAYPAL_SANDBOX_WEBHOOK_ID'''.split()


def main():
    private = ROOT/'.env.supabase.local'
    set_key(str(private), 'CLARORA_PUBLIC_URL', 'https://clarora-market-research.vercel.app')
    values = {**dotenv_values(ROOT/'.env'), **dotenv_values(private)}
    for key in KEYS:
        value = values.get(key)
        if not value:
            continue
        result = subprocess.run(['node', str(CLI), 'env', 'add', key, 'production', '--force'],
                                input=value, text=True, encoding='utf-8', errors='replace',
                                capture_output=True, cwd=ROOT)
        if result.returncode:
            # Deliberately omit CLI output, which may echo rejected values.
            raise RuntimeError('Vercel environment upload failed for '+key)
        print('Configured '+key, flush=True)


if __name__ == '__main__':
    main()
