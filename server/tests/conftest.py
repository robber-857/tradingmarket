import pytest
import os
from urllib.parse import urlparse


@pytest.fixture(autouse=True)
def no_background_network(monkeypatch, tmp_path):
    test_url = os.getenv('TEST_DATABASE_URL')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    if test_url:
        parsed = urlparse(test_url)
        if parsed.hostname not in ('127.0.0.1', 'localhost') or not parsed.path.endswith('_test'):
            raise RuntimeError('TEST_DATABASE_URL must point to a loopback database ending in _test')
        import psycopg
        from pathlib import Path
        with psycopg.connect(test_url, autocommit=True) as c:
            c.execute(Path('supabase/migrations/202611100001_clarora.sql').read_text(), prepare=False)
            tables = c.execute("SELECT tablename FROM pg_tables WHERE schemaname='clarora'").fetchall()
            from psycopg import sql
            c.execute(sql.SQL('TRUNCATE {} CASCADE').format(sql.SQL(',').join(sql.Identifier('clarora', t[0]) for t in tables)))
        monkeypatch.setenv('DATABASE_URL', test_url)
    monkeypatch.setenv('CLARORA_DATABASE', str(tmp_path / 'membership.sqlite3'))
    monkeypatch.setenv('CLARORA_MODE', 'local')
    # Tests exercise ingestion with explicit fixtures, never live polling on app startup.
    monkeypatch.setenv('NEWS_BACKGROUND_ENABLED', '0')
    monkeypatch.setenv('PUBLIC_FORECAST_BACKGROUND_ENABLED', '0')
    from server import public_forecasts
    monkeypatch.setattr(public_forecasts, 'STORE', tmp_path / 'public-forecasts.json')
