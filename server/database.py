"""Portable PostgreSQL transactions; SQLite is only the local compatibility backend.

Short transactions share a database advisory lock during the internal beta.
This preserves SQLite's serialized read/check/write semantics across instances.
No network provider calls may be made while holding a database context.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3


def database_url():
    return os.getenv('DATABASE_URL', '').strip()


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


def postgres_sql(query):
    # Split quoted strings/identifiers so placeholders and the legacy end column
    # are translated only in SQL code, never in literal values.
    parts = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")", query)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'\bend\b', '"end"', parts[i]).replace('?', '%s')
        parts[i] = re.sub(r'\binstr\(', 'strpos(', parts[i])
    query = ''.join(parts)
    if re.match(r'\s*INSERT OR IGNORE\b', query, re.I):
        query = re.sub(r'INSERT OR IGNORE', 'INSERT', query, count=1, flags=re.I).rstrip(';') + ' ON CONFLICT DO NOTHING'
    return query


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, query, params=()):
        if query.strip().upper() == 'BEGIN IMMEDIATE':
            # The transaction lock is already held before any reads.
            return self.raw.execute('SELECT 1')
        return self.raw.execute(postgres_sql(query), params)


@contextmanager
def connect(path=None, namespace='membership'):
    url = database_url()
    if url:
        import psycopg
        with psycopg.connect(url, row_factory=row_factory, prepare_threshold=None,
                             connect_timeout=10) as raw:
            raw.execute('SET LOCAL search_path TO clarora')
            raw.execute("SET LOCAL lock_timeout = '15s'")
            raw.execute("SET LOCAL statement_timeout = '30s'")
            raw.execute('SELECT pg_advisory_xact_lock(%s)', (81261001 if namespace == 'membership' else 81261002,))
            yield Connection(raw)
        return
    if os.getenv('VERCEL') or os.getenv('CLARORA_MODE') == 'public':
        raise RuntimeError('Public deployments require DATABASE_URL; SQLite fallback is disabled')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute('PRAGMA foreign_keys=ON')
    if namespace == 'membership':
        raw.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
    else:
        raw.execute('CREATE TABLE IF NOT EXISTS editions (day TEXT PRIMARY KEY, status TEXT, attempts INTEGER, updated TEXT, payload TEXT, error TEXT)')
    try:
        yield raw
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()
