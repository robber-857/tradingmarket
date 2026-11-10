"""Apply portable schema, optionally import a stopped SQLite installation.

Run from repository root: python -m scripts.migrate_database --apply-schema
Then: python -m scripts.migrate_database --sqlite server/cache/membership.sqlite3
Uses DATABASE_URL; never prints the connection string or customer rows.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import psycopg
from psycopg import sql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TABLES = ['users', 'login_tokens', 'sessions', 'grants', 'usage', 'conversations',
          'saved', 'throttle', 'benefit_reads', 'billing_orders', 'billing_payments',
          'billing_refunds', 'billing_events', 'manual_grants', 'admin_actions', 'admin_requests']


def import_sqlite(connection, source, tables):
    if not source.is_file():
        raise ValueError('SQLite source does not exist')
    db = sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        db.execute('BEGIN')  # Consistent, read-only source snapshot.
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise ValueError('SQLite integrity check failed')
        present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {}
        for table in tables:
            if table not in present:
                continue
            target = sql.Identifier('clarora', table)
            if connection.execute(sql.SQL('SELECT count(*) FROM {}').format(target)).fetchone()[0]:
                raise ValueError('Import requires empty target table: '+table)
            rows = db.execute('SELECT * FROM "'+table+'"')
            columns = [d[0] for d in rows.description]
            insert = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                target, sql.SQL(',').join(map(sql.Identifier, columns)),
                sql.SQL(',').join(sql.Placeholder() for _ in columns))
            count = 0
            for row in rows:
                connection.execute(insert, row)
                count += 1
            actual = connection.execute(sql.SQL('SELECT count(*) FROM {}').format(target)).fetchone()[0]
            if actual != count:
                raise ValueError('Row count mismatch: '+table)
            counts[table] = count
        return counts
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-schema', action='store_true')
    parser.add_argument('--sqlite', type=Path)
    parser.add_argument('--briefs', type=Path)
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    url = os.getenv('DATABASE_URL')
    if not url:
        parser.error('Set DATABASE_URL in the local environment; do not pass it on the command line')
    if args.apply_schema:
        with psycopg.connect(url, autocommit=True, prepare_threshold=None) as c:
            c.execute((ROOT/'supabase/migrations/202611100001_clarora.sql').read_text(), prepare=False)
        print('Schema applied')
    if args.sqlite or args.briefs:
        counts = {}
        with psycopg.connect(url, prepare_threshold=None) as c:
            c.execute('SELECT pg_advisory_xact_lock(81261001)')
            c.execute('SELECT pg_advisory_xact_lock(81261002)')
            if args.sqlite:
                counts.update(import_sqlite(c, args.sqlite, TABLES))
            if args.briefs:
                counts.update(import_sqlite(c, args.briefs, ['editions']))
        print('Import committed; verified row counts:', counts)


if __name__ == '__main__':
    main()
