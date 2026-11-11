"""Manual account provisioning, separate from payments and administrator roles."""
import json
import re
import secrets
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from . import membership as m

router = APIRouter(prefix='/api/admin')


class Provision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    plan: Literal['free', 'research', 'advanced', 'expert']
    days: int = Field(default=30, ge=1, le=366, strict=True)
    reason: str = Field(min_length=2, max_length=500)
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


class Revoke(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=3, max_length=500)


def note(value, minimum=3):
    value = value.strip()
    if len(value) < minimum:
        raise HTTPException(422, f'请填写至少{minimum}个字的操作原因。')
    return value


def audit(db, actor, user_id, action, detail):
    db.execute('INSERT INTO admin_actions VALUES (?,?,?,?,?,?)',
               (secrets.token_hex(16), actor['id'], user_id, action,
                json.dumps(detail, ensure_ascii=False), time.time()))


@router.get('/users')
def users(request: Request, response: Response, q: str = Query('', max_length=254),
          offset: int = Query(0, ge=0)):
    m.require_admin(request)
    response.headers['Cache-Control'] = 'no-store'
    with m.database() as db:
        args = (q.strip().lower(),)
        total = db.execute('SELECT count(*) FROM users WHERE instr(email,?)>0', args).fetchone()[0]
        rows = db.execute('SELECT * FROM users WHERE instr(email,?)>0 ORDER BY created DESC,id LIMIT 10 OFFSET ?',
                          (*args, offset)).fetchall()
        items = [{**dict(row), **m.entitlement(db, row['id'])} for row in rows]
    return {'items': items, 'total': total, 'offset': offset, 'pageSize': 10}


@router.get('/users/{user_id}')
def detail(user_id: str, request: Request, response: Response):
    m.require_admin(request)
    response.headers['Cache-Control'] = 'no-store'
    with m.database() as db:
        user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, '账号不存在。')
        grants = [dict(row) for row in db.execute(
            'SELECT g.id,g.plan,g.start,g.end,g.revoked,mg.reason,mg.actor_id,'
            '(mg.grant_id IS NOT NULL) AS manual FROM grants g '
            'LEFT JOIN manual_grants mg ON mg.grant_id=g.id WHERE g.user_id=? ORDER BY g.start DESC', (user_id,))]
        actions = [{**dict(row), 'detail': json.loads(row['detail'])} for row in db.execute(
            'SELECT a.*,u.email AS actor_email FROM admin_actions a JOIN users u ON u.id=a.actor_id '
            'WHERE a.user_id=? ORDER BY a.created DESC LIMIT 100', (user_id,))]
    return {'account': m.account(dict(user)), 'grants': grants, 'actions': actions}


@router.post('/users')
def provision(body: Provision, request: Request, response: Response):
    actor = m.require_admin(request)
    response.headers['Cache-Control'] = 'no-store'
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^\s@\r\n]+@[^\s@\r\n]+\.[^\s@\r\n]+', email):
        raise HTTPException(422, '请输入有效邮箱地址。')
    reason = note(body.reason, minimum=2)
    fingerprint = m.digest(json.dumps([email, body.plan, body.days, reason]))
    now = time.time()
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM admin_requests WHERE actor_id=? AND key=?',
                              (actor['id'], body.request_key)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, '请求编号已用于其他操作，请重新提交。')
            return json.loads(previous['result'])
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        created = user is None
        user_id = user['id'] if user else secrets.token_hex(16)
        if created:
            db.execute('INSERT INTO users VALUES (?,?,?)', (user_id, email, now))
            audit(db, actor, user_id, 'create_account', {'reason': reason})
        grant_id = None
        if body.plan != 'free':
            # Never mask a paid/refund-frozen entitlement or silently reset usage.
            overlap = db.execute('SELECT 1 FROM grants WHERE user_id=? AND end>? AND revoked!=1 LIMIT 1',
                                 (user_id, now)).fetchone()
            if overlap:
                raise HTTPException(409, '该账号已有未结束的授权。手动授权请先撤销；付款或退款中的权益请到付款管理处理。')
            grant_id = 'manual-'+secrets.token_hex(16)
            end = now + body.days*86400
            db.execute('INSERT INTO grants VALUES (?,?,?,?,?,?,0)',
                       (grant_id, user_id, body.plan, now, end, json.dumps(m.PLANS[body.plan]['limits'])))
            db.execute('INSERT INTO manual_grants VALUES (?,?,?,?)', (grant_id, actor['id'], reason, now))
            audit(db, actor, user_id, 'grant_membership',
                  {'grantId': grant_id, 'plan': body.plan, 'days': body.days, 'expiresAt': end, 'reason': reason})
        result = {'userId': user_id, 'created': created, 'grantId': grant_id}
        db.execute('INSERT INTO admin_requests VALUES (?,?,?,?)',
                   (actor['id'], body.request_key, fingerprint, json.dumps(result)))
    return result


@router.post('/grants/{grant_id}/revoke')
def revoke(grant_id: str, body: Revoke, request: Request, response: Response):
    actor = m.require_admin(request)
    response.headers['Cache-Control'] = 'no-store'
    reason = note(body.reason)
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        grant = db.execute('SELECT g.* FROM grants g JOIN manual_grants mg ON mg.grant_id=g.id WHERE g.id=?',
                           (grant_id,)).fetchone()
        if not grant:
            raise HTTPException(404, '手动授权不存在；付款权益不能在此撤销。')
        if grant['revoked'] != 1:
            db.execute('UPDATE grants SET revoked=1 WHERE id=?', (grant_id,))
            audit(db, actor, grant['user_id'], 'revoke_membership', {'grantId': grant_id, 'reason': reason})
    return {'ok': True}
