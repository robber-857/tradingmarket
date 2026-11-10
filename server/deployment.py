"""Hosting-independent configuration checks and cross-instance job leases."""
import os
import secrets
import time
from urllib.parse import urlparse
from . import membership as m
from .database import database_url


def validate():
    if not os.getenv('VERCEL'):
        return
    required = ['DATABASE_URL', 'CLARORA_PUBLIC_URL', 'S3_BUCKET', 'CRON_SECRET']
    if os.getenv('EMAIL_LOGIN_ENABLED', '1') != '0':
        required += ['SMTP_HOST', 'SMTP_FROM']
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError('Missing deployment settings: ' + ', '.join(missing))
    if m.local_mode() or os.getenv('CLARORA_STORAGE_BACKEND') != 's3':
        raise RuntimeError('Vercel requires public mode and S3 persistence')
    if urlparse(os.environ['CLARORA_PUBLIC_URL']).scheme != 'https':
        raise RuntimeError('CLARORA_PUBLIC_URL must use HTTPS')
    if 'sslmode=' not in database_url() or 'sslmode=disable' in database_url():
        raise RuntimeError('DATABASE_URL must explicitly enable TLS')


def acquire(name, ttl=600):
    if not database_url():
        return 'local'
    owner = secrets.token_hex(16)
    with m.database() as db:
        db.execute('DELETE FROM job_leases WHERE name=? AND expires<?', (name, time.time()))
        row = db.execute('INSERT INTO job_leases VALUES (?,?,?) ON CONFLICT(name) DO NOTHING RETURNING owner',
                         (name, owner, time.time()+ttl)).fetchone()
    return owner if row else None


def release(name, owner):
    if not database_url() or not owner:
        return
    with m.database() as db:
        db.execute('DELETE FROM job_leases WHERE name=? AND owner=?', (name, owner))
