"""Google authorization-code login; identity and session stay on the server."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, HTTPException
from starlette.responses import RedirectResponse
from . import membership as m
from .member_api import origin, email_login_enabled

router = APIRouter(prefix='/api/auth')
ROUTES = {'overview','financials','fundamentals','news','calendar','daily','options','strategies','watchlist','academy','membership','admin','settings','capital'}


def safe_next(value):
    return value if value in ROUTES else 'overview'


def google_enabled():
    return bool(m.config('GOOGLE_CLIENT_ID') and m.config('GOOGLE_CLIENT_SECRET'))


@router.get('/config')
def config():
    return {'google': google_enabled(), 'email': email_login_enabled(), 'local': m.local_mode()}


@router.get('/google/start')
def start(request: Request, next: str = 'overview'):
    if not google_enabled():
        return RedirectResponse('/#login?error=google_unavailable')
    m.throttle('oauth:'+(request.client.host if request.client else 'unknown'), 20)
    state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with m.database() as db:
        db.execute('DELETE FROM auth_pending WHERE expires<?', (time.time(),))
        db.execute('INSERT INTO auth_pending VALUES (?,?,?)', (m.digest(state), json.dumps({'browser':m.digest(browser), 'verifier':verifier, 'next':safe_next(next)}), time.time()+600))
    response = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
        'client_id':m.config('GOOGLE_CLIENT_ID'), 'redirect_uri':origin()+'/api/auth/google/callback',
        'response_type':'code', 'scope':'openid email', 'state':state,
        'code_challenge':challenge, 'code_challenge_method':'S256', 'prompt':'select_account'}))
    response.set_cookie('clarora_oauth', browser, httponly=True, secure=not m.local_mode(), samesite='lax', max_age=600, path='/api/auth/google')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/google/callback')
async def callback(request: Request, state: str = '', code: str = '', error: str = ''):
    def failure(reason):
        response = RedirectResponse('/#login?error='+reason, status_code=303)
        response.delete_cookie('clarora_oauth', path='/api/auth/google')
        response.headers['Cache-Control'] = 'no-store'
        return response
    if not state or len(state)>128 or not google_enabled():
        return failure('google_failed')
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM auth_pending WHERE hash=? AND expires>?', (m.digest(state),time.time())).fetchone()
        metadata = json.loads(row['payload']) if row else {}
        if not row or not secrets.compare_digest(metadata.get('browser',''), m.digest(request.cookies.get('clarora_oauth',''))):
            return failure('google_failed')
        db.execute('DELETE FROM auth_pending WHERE hash=?', (m.digest(state),))
    if error or not code or len(code)>4096:
        return failure('google_cancelled')
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await client.post('https://oauth2.googleapis.com/token', data={
                'code':code,'client_id':m.config('GOOGLE_CLIENT_ID'),'client_secret':m.config('GOOGLE_CLIENT_SECRET'),
                'redirect_uri':origin()+'/api/auth/google/callback','grant_type':'authorization_code','code_verifier':metadata['verifier']})
            token.raise_for_status()
            identity = await client.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization':'Bearer '+token.json()['access_token']})
            identity.raise_for_status()
            info = identity.json()
        email = info.get('email','').strip().lower()
        if info.get('email_verified') is not True or not info.get('sub') or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            return failure('google_failed')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return failure('google_failed')
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        linked = db.execute('SELECT user_id FROM oauth_identities WHERE subject=?', (info['sub'],)).fetchone()
        if linked:
            uid = linked['user_id']
        else:
            # Only Google's authoritative Gmail / Workspace emails may link an existing account.
            existing = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if existing and not (email.endswith('@gmail.com') or info.get('hd')):
                return failure('email_link_required')
            db.execute('INSERT OR IGNORE INTO users VALUES (?,?,?)', (secrets.token_hex(16),email,time.time()))
            uid = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()['id']
            db.execute('INSERT INTO oauth_identities VALUES (?,?)', (info['sub'],uid))
        session = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (m.digest(session),uid,time.time()+30*86400))
        old = request.cookies.get(m.COOKIE)
        if old:
            db.execute('DELETE FROM sessions WHERE hash=?', (m.digest(old),))
    response = RedirectResponse('/#'+safe_next(metadata['next']), status_code=303)
    response.set_cookie(m.COOKIE,session,httponly=True,secure=not m.local_mode(),samesite='lax',max_age=30*86400,path='/')
    response.delete_cookie('clarora_oauth',path='/api/auth/google')
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='no-referrer'
    return response
