"""ToC catalogue, durable account sessions and atomic metering.

Public mode fails closed. Local mode preserves the existing single-user research
workflow; it must never be exposed through a public reverse proxy.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from dotenv import dotenv_values
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
DEPTH = ContextVar('clarora_analysis_depth', default='standard')
COOKIE = 'clarora_session'
PLANS = {
    'free': {'name': '免费体验', 'prices': {'cny': 0, 'aud': 0, 'usd': 0},
             'limits': {'ai': 5, 'deep': 1, 'sentiment': 0}, 'all_courses': False},
    'research': {'name': '研究会员', 'prices': {'cny': 12900, 'aud': 2900, 'usd': 1900},
                 'limits': {'ai': 100, 'deep': 10, 'sentiment': 10}, 'all_courses': False},
    'advanced': {'name': '高级会员', 'prices': {'cny': 24900, 'aud': 5500, 'usd': 3900},
                 'limits': {'ai': 300, 'deep': 40, 'sentiment': 50}, 'all_courses': True},
    'expert': {'name': '专家会员', 'prices': {'cny': 49900, 'aud': 10900, 'usd': 7900},
               'limits': {'ai': 800, 'deep': 100, 'sentiment': 150}, 'all_courses': True},
}
WEEK = {'prices': {'cny': 4900, 'aud': 1000, 'usd': 700},
        'limits': {'ai': 25, 'deep': 3, 'sentiment': 3}, 'days': 7, 'plan': 'research'}


def config(key, default=''):
    return os.environ.get(key, dotenv_values(ROOT / '.env').get(key) or default)


def local_mode():
    return config('CLARORA_MODE', 'local') == 'local'


def db_path():
    return Path(config('CLARORA_DATABASE', str(ROOT / 'server' / 'cache' / 'membership.sqlite3')))


@contextmanager
def database():
    from .database import connect
    with connect(db_path(), 'membership') as conn:
        yield conn


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(key, limit=5, seconds=900):
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM throttle WHERE created<?', (now - 86400,))
        count = db.execute('SELECT count(*) FROM throttle WHERE key=? AND created>?', (key, now-seconds)).fetchone()[0]
        if count >= limit:
            raise HTTPException(429, '请求过于频繁，请稍后再试。')
        db.execute('INSERT INTO throttle VALUES (?,?)', (key, now))


def issue_login(email):
    token = secrets.token_urlsafe(32)
    with database() as db:
        db.execute('DELETE FROM login_tokens WHERE email=? OR expires<?', (email, time.time()))
        db.execute('INSERT INTO login_tokens VALUES (?,?,?)', (digest(token), email, time.time()+900))
    return token


def redeem_login(token):
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM login_tokens WHERE hash=? AND expires>?', (digest(token), now)).fetchone()
        if not row:
            raise HTTPException(400, '登录链接无效或已过期，请重新获取。')
        db.execute('DELETE FROM login_tokens WHERE hash=?', (digest(token),))
        db.execute('INSERT OR IGNORE INTO users VALUES (?,?,?)', (secrets.token_hex(16), row['email'], now))
        user = dict(db.execute('SELECT * FROM users WHERE email=?', (row['email'],)).fetchone())
        session = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(session), user['id'], now+30*86400))
    return session, user


def current_user(request, required=False):
    token = request.cookies.get(COOKIE, '')
    with database() as db:
        row = db.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id '
                         'WHERE sessions.hash=? AND sessions.expires>?', (digest(token), time.time())).fetchone()
    if required and not row:
        raise HTTPException(401, '请先登录霁明账户。')
    return dict(row) if row else None


def entitlement(db, user_id, now=None):
    now = now or time.time()
    rows = db.execute('SELECT * FROM grants WHERE user_id=? AND start<=? AND end>? AND revoked=0',
                      (user_id, now, now)).fetchall()
    if rows:
        rank = {name: i for i, name in enumerate(PLANS)}
        row = max(rows, key=lambda r: (rank.get(r['plan'], -1), r['end']))
        return {'plan': row['plan'], 'period': row['id'], 'expiresAt': row['end'], 'limits': json.loads(row['limits'])}
    month = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m')
    return {'plan': 'free', 'period': 'free:'+month, 'expiresAt': None, 'limits': PLANS['free']['limits']}


def account(user):
    with database() as db:
        info = entitlement(db, user['id'])
        counts = {r['bucket']: r['n'] for r in db.execute(
            "SELECT bucket,count(*) AS n FROM usage WHERE user_id=? AND period=? AND state IN ('pending','complete') GROUP BY bucket",
            (user['id'], info['period']))}
    return {**info, 'user': {'id': user['id'], 'email': user['email']}, 'isAdmin': is_admin(user),
            'planName': PLANS[info['plan']]['name'], 'allCourses': PLANS[info['plan']]['all_courses'],
            'usage': {k: {'limit': n, 'used': counts.get(k, 0), 'remaining': max(0, n-counts.get(k, 0))}
                      for k, n in info['limits'].items()}}


def is_admin(user):
    if not user:
        return False
    emails = {value.strip().lower() for value in config('CLARORA_ADMIN_EMAILS').split(',') if value.strip()}
    ids = {value.strip() for value in config('CLARORA_ADMIN_USER_IDS').split(',') if value.strip()}
    return user['email'].lower() in emails or user['id'] in ids


def require_admin(request):
    user = current_user(request, True)
    if not is_admin(user):
        raise HTTPException(403, '需要账号管理员权限。')
    return user


def reserve(user_id, key, fingerprint, bucket):
    """Reserve before upstream work; concurrent calls cannot overspend a bucket.

    Interrupted reservations stay pending for explicit reconciliation rather than
    silently refunding a provider call that may actually have completed.
    """
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM usage WHERE user_id=? AND key=?', (user_id, key)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint:
                raise HTTPException(409, '同一请求编号不能用于不同分析。')
            if old['state'] in ('complete', 'fallback'):
                return json.loads(old['response'])
            if old['state'] == 'pending':
                raise HTTPException(409, '该分析正在处理或等待恢复，请勿重复提交。')
            db.execute('DELETE FROM usage WHERE user_id=? AND key=?', (user_id, key))
        info = entitlement(db, user_id)
        if bucket == 'sentiment':
            raise HTTPException(503, '市场情绪数据服务尚未开放，不扣额度。')
        used = db.execute("SELECT count(*) FROM usage WHERE user_id=? AND period=? AND bucket=? AND state IN ('pending','complete')",
                          (user_id, info['period'], bucket)).fetchone()[0]
        if used >= info['limits'].get(bucket, 0):
            raise HTTPException(402, '本周期该类 AI 额度已用完，请查看会员中心。')
        db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?,NULL)',
                   (user_id, key, fingerprint, info['period'], bucket, 'pending', time.time()))
    return None


def finish(user_id, key, result=None):
    with database() as db:
        db.execute('UPDATE usage SET state=?,response=? WHERE user_id=? AND key=? AND state=?',
                   (('fallback' if result.get('chargeable') is False else 'complete') if result is not None else 'failed', json.dumps(result, ensure_ascii=False) if result is not None else None,
                    user_id, key, 'pending'))
        if result and result.get('conversationId'):
            db.execute('INSERT OR IGNORE INTO conversations VALUES (?,?)', (result['conversationId'], user_id))


def check_conversation(user_id, conversation_id):
    if not conversation_id:
        return
    with database() as db:
        row = db.execute('SELECT user_id FROM conversations WHERE id=?', (conversation_id,)).fetchone()
    if not row or row['user_id'] != user_id:
        raise HTTPException(403, '该研究会话不属于当前账户，请重新开始分析。')
