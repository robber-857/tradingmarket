"""Account/entitlement APIs. No client can grant itself a paid membership."""
import asyncio
from email.message import EmailMessage
import json
import re
import secrets
import smtplib
import ssl
import time
from typing import Literal
from urllib.parse import urlparse, urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from . import membership as m
from . import payment_providers

router = APIRouter(prefix='/api')


def email_login_enabled():
    return m.local_mode() or (m.config('EMAIL_LOGIN_ENABLED', '1') != '0'
                              and bool(m.config('SMTP_HOST') and m.config('SMTP_FROM'))
                              and (not m.config('SMTP_USER') or bool(m.config('SMTP_PASSWORD'))))


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(default="", max_length=30)
    intent: Literal["login", "register"] = "login"
    next: str = Field(default="overview", max_length=200)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['watchlist', 'research', 'strategy', 'course_progress']
    title: str = Field(min_length=1, max_length=120)
    payload: dict


def origin():
    value = m.config('CLARORA_PUBLIC_URL', 'http://127.0.0.1:5173').rstrip('/')
    parsed = urlparse(value)
    if not m.local_mode() and (parsed.scheme != 'https' or not parsed.netloc):
        raise HTTPException(503, '网站地址尚未完成配置。')
    return value


def send_login(email, link):
    host = m.config('SMTP_HOST')
    sender = m.config('SMTP_FROM')
    if not host or not sender:
        raise HTTPException(503, '登录邮件服务尚未开放，请稍后再试。')
    message = EmailMessage()
    message['Subject'] = '霁明 Clarora 登录链接'
    message['From'], message['To'] = sender, email
    message.set_content(f'请打开以下链接登录霁明，15 分钟内有效且只能使用一次。\n\n{link}\n\n如非本人操作，请忽略此邮件。')
    try:
        with smtplib.SMTP(host, int(m.config('SMTP_PORT', '587')), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if m.config('SMTP_USER'):
                smtp.login(m.config('SMTP_USER'), m.config('SMTP_PASSWORD'))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(503, '邮件暂时发送失败，请稍后重试。') from exc


@router.get('/membership/plans')
def plans():
    return {'plans': [{'id': key, **value} for key, value in m.PLANS.items()], 'weekPass': m.WEEK,
            'currencies': ['cny', 'aud', 'usd'], 'localMode': m.local_mode(),
            'emailLoginEnabled': email_login_enabled(),
            'salesEnabled': False, 'sentimentAvailable': False, 'billing':payment_providers.availability(),
            'notice': '试定价；正在完成付费上线准备，当前未开放购买。市场情绪额度为规划，不扣费、不承诺已接入。',
            'paymentMethods': [
                {'name': 'Stripe · 银行卡 / Apple Pay', 'currencies': ['aud', 'usd'], 'status': '已实现测试接入；待真实渠道联调'},
                {'name': '支付宝', 'currencies': ['cny'], 'status': 'Stripe 测试单次购买；到期手动续购'},
                {'name': 'PayPal', 'currencies': ['aud', 'usd'], 'status': 'Sandbox 单次购买；到期手动续购'},
            ]}


@router.post('/auth/request-link')
async def request_link(body: EmailRequest, request: Request):
    if not email_login_enabled():
        raise HTTPException(503, '内测预览期间邮箱登录暂未开放。')
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^\s@\r\n]+@[^\s@\r\n]+\.[^\s@\r\n]+', email):
        raise HTTPException(422, '请输入有效邮箱地址。')
    m.throttle('email:'+m.digest(email))
    m.throttle('ip:'+(request.client.host if request.client else 'unknown'), 15)
    if not m.local_mode() and not m.config('SMTP_HOST'):
        raise HTTPException(503, '登录邮件服务尚未开放。')
    phone = body.phone.strip()
    if phone and not re.fullmatch(r'\+?[0-9 ()-]{6,30}', phone):
        raise HTTPException(422, '请输入有效手机号，或留空。')
    token = m.issue_login(email)
    from .auth import safe_next
    with m.database() as db:
        db.execute('INSERT INTO auth_pending VALUES (?,?,?)', (m.digest(token), json.dumps({'phone': phone if body.intent == 'register' else '', 'next': safe_next(body.next)}), time.time()+900))
    link = origin()+'/#login?'+urlencode({'token':token, 'next':safe_next(body.next)})
    if m.local_mode():
        return {'message': '本地开发模式：使用以下一次性链接登录。公网模式不会返回登录链接。', 'localLoginUrl': link}
    await asyncio.to_thread(send_login, email, link)
    return {'message': '登录链接已发送，请检查邮箱。'}


@router.post('/auth/verify')
def verify(body: TokenRequest, request: Request, response: Response):
    m.throttle('verify:'+(request.client.host if request.client else 'unknown'), 20)
    session, user = m.redeem_login(body.token)
    destination = 'overview'
    with m.database() as db:
        pending = db.execute('SELECT * FROM auth_pending WHERE hash=? AND expires>?', (m.digest(body.token), time.time())).fetchone()
        if pending:
            metadata = json.loads(pending['payload'])
            destination = metadata['next']
            if metadata['phone']:
                db.execute('INSERT INTO user_profiles VALUES (?,?) ON CONFLICT(user_id) DO NOTHING', (user['id'], metadata['phone']))
            db.execute('DELETE FROM auth_pending WHERE hash=?', (m.digest(body.token),))
    response.set_cookie(m.COOKIE, session, httponly=True, secure=not m.local_mode(), samesite='lax', max_age=30*86400, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {**m.account(user), "next": destination}


@router.get('/account')
def account(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    user = m.current_user(request)
    return m.account(user) if user else {'user': None, 'plan': 'free', 'planName': '未登录', 'localMode': m.local_mode()}


@router.post('/auth/logout')
def logout(request: Request, response: Response):
    with m.database() as db:
        db.execute('DELETE FROM sessions WHERE hash=?', (m.digest(request.cookies.get(m.COOKIE, '')),))
    response.delete_cookie(m.COOKIE, path='/')
    return {'ok': True}


@router.get('/account/saved')
def saved(request: Request, response: Response):
    user = m.current_user(request, True)
    response.headers['Cache-Control'] = 'no-store'
    with m.database() as db:
        rows = db.execute('SELECT * FROM saved WHERE user_id=? ORDER BY updated DESC', (user['id'],)).fetchall()
    return {'items': [{'id': r['id'], 'kind': r['kind'], 'title': r['title'], 'payload': json.loads(r['payload']), 'updated': r['updated']} for r in rows]}


@router.put('/account/saved/{item_id}')
def save(item_id: str, body: SaveRequest, request: Request):
    user = m.current_user(request, True)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', item_id):
        raise HTTPException(422, '保存编号无效。')
    payload = json.dumps(body.payload, ensure_ascii=False)
    if len(payload.encode()) > 200_000:
        raise HTTPException(413, '研究记录过大，请缩减后保存。')
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute('SELECT count(*) FROM saved WHERE user_id=?', (user['id'],)).fetchone()[0]
        exists = db.execute('SELECT 1 FROM saved WHERE user_id=? AND id=?', (user['id'], item_id)).fetchone()
        if count >= 200 and not exists:
            raise HTTPException(409, '已达到两百条保存记录，请先整理研究库。')
        db.execute('INSERT INTO saved VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET '
                   'kind=excluded.kind,title=excluded.title,payload=excluded.payload,updated=excluded.updated',
                   (user['id'], item_id, body.kind, body.title, payload, time.time()))
    return {'ok': True}


@router.delete('/account/saved/{item_id}')
def remove(item_id: str, request: Request):
    user = m.current_user(request, True)
    with m.database() as db:
        db.execute('DELETE FROM saved WHERE user_id=? AND id=?', (user['id'], item_id))
    return {'ok': True}


AI_PATHS = {'/api/news/explain', '/api/macro/explain', '/api/options/explain'}


async def access_middleware(request, call_next):
    """Meter real analyses, not cached public briefs or deterministic maths."""
    key = user = None
    lease_name = lease_owner = None
    token = None
    try:
        # Provider callbacks authenticate raw bodies by their own signatures, not
        # browser cookies/Origin. No other route bypasses these checks.
        if request.method=='POST' and request.url.path in ('/api/billing/webhooks/stripe','/api/billing/webhooks/paypal'):
            return await call_next(request)
        if m.local_mode() and request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, '本地模式仅允许本机访问；公网部署需启用 public 模式。')
        if m.local_mode() and request.url.hostname not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
            raise HTTPException(403, '本地模式不能使用公网域名。')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            source = request.headers.get('origin')
            allowed = {origin()}
            if m.local_mode():
                allowed |= {'http://localhost:5173', 'http://127.0.0.1:5173', 'http://127.0.0.1:4173'}
            if source and source not in allowed:
                raise HTTPException(403, '请求来源不受信任。')
            if not source and not m.local_mode():
                raise HTTPException(403, '缺少请求来源，请从霁明网页操作。')
        path = request.url.path
        ai = request.method == 'POST' and (path in AI_PATHS or bool(re.fullmatch(r'/api/research/[^/]+/explain', path)))
        if not m.local_mode() and path == '/api/briefs/generate':
            raise HTTPException(403, '每日公共简报由后台调度生成。')
        if not m.local_mode() and path == '/api/macro/institution-translation':
            signed = m.current_user(request, True)
            m.throttle('translation:'+signed['id'], 30, 60)
        if ai:
            if int(request.headers.get('content-length', '0')) > 100_000:
                raise HTTPException(413, '分析请求过大。')
            body = await request.json()
            if not isinstance(body, dict) or body.get('analysis_depth', 'standard') not in ('standard', 'deep'):
                raise HTTPException(422, '分析深度无效。')
            depth = body.get('analysis_depth', 'standard')
            token = m.DEPTH.set(depth)
            user = m.current_user(request)
            if not user and not m.local_mode():
                raise HTTPException(401, '请先登录后使用 AI 分析。')
            if user:
                m.throttle('ai:'+user['id'], 12, 60)
                m.check_conversation(user['id'], body.get('conversation_id'))
                key = request.headers.get('Idempotency-Key', secrets.token_hex(16))
                if not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', key):
                    raise HTTPException(422, '分析请求编号无效。')
                fingerprint = m.digest(path+json.dumps(body, sort_keys=True))
                cached = m.reserve(user['id'], key, fingerprint, 'deep' if depth == 'deep' else 'ai')
                if cached is not None:
                    return JSONResponse(cached, headers={'Cache-Control': 'no-store', 'X-Clarora-Replayed': 'true'})
                if body.get('conversation_id'):
                    from .deployment import acquire
                    lease_name = 'conversation:' + body['conversation_id']
                    lease_owner = acquire(lease_name)
                    if not lease_owner:
                        m.finish(user['id'], key)
                        raise HTTPException(409, '该会话正在生成解读，请稍后再试。')
                response = await call_next(request)
                raw = b''.join([chunk async for chunk in response.body_iterator])
                result = json.loads(raw) if response.status_code < 300 else None
                m.finish(user['id'], key, result)
                return Response(raw, status_code=response.status_code, headers={**dict(response.headers), 'Cache-Control': 'no-store'}, media_type='application/json')
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if user and key:
            m.finish(user['id'], key)
        return JSONResponse({'detail': '请求或分析响应格式无效。'}, status_code=422)
    except Exception:
        if user and key:
            m.finish(user['id'], key)
        raise
    finally:
        if lease_owner:
            from .deployment import release
            release(lease_name, lease_owner)
        if token is not None:
            m.DEPTH.reset(token)
