import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import pytest
from server.database import postgres_sql
from server import membership as m


def test_sql_translation_keeps_literals_and_binds_values():
    assert postgres_sql("SELECT 'end?', end FROM grants WHERE id=?") == "SELECT 'end?', \"end\" FROM grants WHERE id=%s"


@pytest.fixture
def postgres():
    if not os.getenv('TEST_DATABASE_URL'):
        pytest.skip('Requires isolated TEST_DATABASE_URL')
    return os.environ['TEST_DATABASE_URL']


def test_postgres_rolls_back_and_enforces_foreign_keys(postgres):
    with pytest.raises(RuntimeError):
        with m.database() as db:
            db.execute('INSERT INTO users VALUES (?,?,?)', ('rollback', 'rollback@example.invalid', time.time()))
            raise RuntimeError('interrupt transaction')
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 0
    import psycopg
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with m.database() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?)', ('hash', 'missing', time.time()+60))


def test_cross_instance_sessions_and_job_leases(postgres):
    from server.session_store import SessionStore
    from server.deployment import acquire, release
    first, second = SessionStore('test'), SessionStore('test')
    first['id'] = {'history': [{'question': 'test'}], 'updated': time.monotonic()}
    assert second['id']['history'][0]['question'] == 'test'
    with ThreadPoolExecutor(max_workers=4) as pool:
        owners = list(pool.map(lambda _: acquire('test-job'), range(4)))
    assert len([owner for owner in owners if owner]) == 1
    owner = next(owner for owner in owners if owner)
    release('test-job', 'wrong-owner')
    assert acquire('test-job') is None
    release('test-job', owner)
    assert acquire('test-job')


def test_sqlite_import_preserves_rows_and_refuses_merge(postgres, tmp_path):
    import psycopg
    from scripts.migrate_database import import_sqlite
    source = tmp_path/'source.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE users(id TEXT, email TEXT, created REAL)')
        db.execute('INSERT INTO users VALUES (?,?,?)', ('original-id', 'test@example.invalid', 123.456789))
    with psycopg.connect(postgres) as c:
        assert import_sqlite(c, source, ['users']) == {'users': 1}
    with m.database() as db:
        row = db.execute('SELECT * FROM users').fetchone()
        assert row['id'] == 'original-id' and row['created'] == 123.456789
    with psycopg.connect(postgres) as c:
        with pytest.raises(ValueError, match='empty target'):
            import_sqlite(c, source, ['users'])


def test_cron_requires_secret(monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import app
    monkeypatch.setenv('CRON_SECRET', 'internal-test-secret')
    with TestClient(app) as client:
        assert client.get('/api/cron/brief').status_code == 401
        assert client.get('/api/cron/brief', headers={'Authorization':'Bearer wrong'}).status_code == 401


def test_cloud_boot_rejects_missing_configuration(monkeypatch):
    from server.deployment import validate
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        validate()


def test_public_preview_disables_login_without_development_link(monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import app
    monkeypatch.setenv('CLARORA_MODE', 'public')
    monkeypatch.setenv('CLARORA_PUBLIC_URL', 'https://clarora.example')
    monkeypatch.setenv('EMAIL_LOGIN_ENABLED', '0')
    with TestClient(app, base_url='https://clarora.example') as client:
        plans = client.get('/api/membership/plans').json()
        assert plans['emailLoginEnabled'] is False
        assert plans['localMode'] is False
        response = client.post('/api/auth/request-link', json={'email':'test@example.invalid'},
                               headers={'Origin':'https://clarora.example'})
        assert response.status_code == 503
        assert 'localLoginUrl' not in response.json()
