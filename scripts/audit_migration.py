"""Read-only comparison of a SQLite backup, cloud PostgreSQL and S3 snapshots.

Never prints credentials, customer rows, tokens, object contents or provider errors.
Does not apply migrations, upload objects, create users or invoke scheduled jobs.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

import httpx
import psycopg
from psycopg import sql
from dotenv import load_dotenv

from scripts.migrate_database import TABLES
from scripts.migrate_objects import FOLDERS

ROOT = Path(__file__).resolve().parents[1]


def compare_backup(connection, source, tables):
    results = {}
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as local:
        local.execute('BEGIN')
        if local.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source integrity check failed')
        present = {r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table not in present:
                continue
            cursor = local.execute('SELECT * FROM "' + table + '"')
            columns = [column[0] for column in cursor.description]
            old = cursor.fetchall()
            # Supabase may default extra_float_digits=0. Binary transfer avoids
            # mistaking rounded timestamp text for corruption of stored doubles.
            current = connection.cursor(binary=True).execute(sql.SQL('SELECT {} FROM {}').format(
                sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier('clarora', table))).fetchall()
            old_set, current_set = Counter(old), Counter(current)
            results[table] = {'backupRows': len(old), 'cloudRows': len(current),
                              'backupRowsStillIdentical': sum((old_set & current_set).values()),
                              'exactMatch': old_set == current_set,
                              'mutable': table in ('sessions', 'login_tokens', 'throttle', 'editions')}
    return results


def audit(env_file, backup):
    if not env_file.is_file():
        raise FileNotFoundError('Explicit environment file is required')
    load_dotenv(env_file, override=True)
    result = {}
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=15) as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        connection.execute("SET LOCAL statement_timeout = '20s'")
        result['tables'] = compare_backup(connection, backup / 'membership.sqlite3', TABLES)
        result['tables'].update(compare_backup(connection, backup / 'daily-briefs.sqlite3', ['editions']))
        result['schemaTables'] = connection.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname='clarora'").fetchone()[0]
        result['invalidConstraints'] = connection.execute(
            "SELECT count(*) FROM pg_constraint WHERE connamespace='clarora'::regnamespace AND NOT convalidated").fetchone()[0]
        result['browserSchemaAccess'] = {role: connection.execute(
            "SELECT has_schema_privilege(%s, 'clarora', 'USAGE')", (role,)).fetchone()[0]
            for role in ('anon', 'authenticated')}
        result['bucketPrivate'] = connection.execute(
            'SELECT NOT public FROM storage.buckets WHERE id=%s', (os.environ['S3_BUCKET'],)).fetchone()[0]
        result['cron'] = [dict(zip(('job', 'schedule', 'active'), row)) for row in connection.execute(
            "SELECT jobname,schedule,active FROM cron.job WHERE jobname LIKE 'clarora-%' ORDER BY jobname")]
        result['cronRecent'] = [dict(zip(('job', 'status', 'runs'), row)) for row in connection.execute(
            "SELECT j.jobname,d.status,count(*) FROM cron.job_run_details d JOIN cron.job j USING(jobid) "
            "WHERE j.jobname LIKE 'clarora-%' AND d.start_time>now()-interval '24 hours' GROUP BY j.jobname,d.status")]
        result['httpJobResponses'] = [dict(zip(('httpStatus', 'timedOut', 'count'), row)) for row in connection.execute(
            "SELECT status_code,timed_out,count(*) FROM net._http_response WHERE created>now()-interval '24 hours' "
            "GROUP BY status_code,timed_out")]

    from server.object_store import ObjectPath
    files = [p for folder in FOLDERS for p in (ROOT/'server'/folder).glob('*.json')]

    def check(path):
        try:
            expected = path.read_text(encoding='utf-8').encode()
            actual = ObjectPath(path.relative_to(ROOT).as_posix()).read_text().encode()
            state = 'identical' if hashlib.sha256(expected).digest() == hashlib.sha256(actual).digest() else 'different'
        except FileNotFoundError:
            state = 'missing'
        except Exception:
            state = 'readError'
        return {'state': state, 'folder': path.parent.name,
                'localModifiedAfterBackup': path.stat().st_mtime > (backup/'membership.sqlite3').stat().st_mtime}

    with ThreadPoolExecutor(max_workers=6) as pool:
        states = list(pool.map(check, files))
    result['objects'] = {state: sum(item['state'] == state for item in states)
                         for state in ('identical', 'different', 'missing', 'readError')}
    result['objects']['sourceFiles'] = len(files)
    result['objectDifferences'] = [item for item in states if item['state'] != 'identical']

    base = os.environ['CLARORA_PUBLIC_URL'].rstrip('/')
    result['publicEndpoints'] = {}
    with httpx.Client(base_url=base, timeout=40) as client:
        for path in ('/api/health', '/api/account', '/api/membership/plans', '/api/billing/status',
                     '/api/briefs', '/api/briefs?day=2026-11-10', '/api/admin/users',
                     '/api/admin/billing/readiness', '/api/cron/brief'):
            response = client.get(path)
            item = {'httpStatus': response.status_code}
            if path == '/api/membership/plans' and response.is_success:
                item.update({key: response.json().get(key) for key in
                             ('localMode', 'emailLoginEnabled', 'salesEnabled')})
            if path == '/api/billing/status' and response.is_success:
                item.update({key: response.json().get(key) for key in ('enabled', 'testMode', 'stripe', 'paypal')})
            result['publicEndpoints'][path] = item
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.env_file, args.backup)
    except Exception as exc:
        print('Audit stopped: ' + type(exc).__name__ + '; provider details suppressed.')
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
