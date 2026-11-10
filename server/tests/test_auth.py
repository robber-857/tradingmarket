import json
from urllib.parse import urlparse, parse_qs
from fastapi.testclient import TestClient
from server.app import app
from server import membership as m, auth
import httpx


def test_authenticated_smtp_is_unavailable_without_password(monkeypatch):
    from server import member_api
    monkeypatch.setattr(m, 'local_mode', lambda: False)
    monkeypatch.setenv('EMAIL_LOGIN_ENABLED','1')
    monkeypatch.setenv('SMTP_HOST','smtp.gmail.com')
    monkeypatch.setenv('SMTP_FROM','sender@gmail.com')
    monkeypatch.setenv('SMTP_USER','sender@gmail.com')
    monkeypatch.setenv('SMTP_PASSWORD','')
    assert not member_api.email_login_enabled()
    monkeypatch.setenv('SMTP_PASSWORD','test-app-password')
    assert member_api.email_login_enabled()


def test_registration_phone_saved_only_after_verification():
    client=TestClient(app)
    result=client.post('/api/auth/request-link',json={'email':'register@example.com','intent':'register','phone':'+61 412 345 678','next':'financials'}).json()
    token=parse_qs(urlparse(result['localLoginUrl']).fragment.split('?')[1])['token'][0]
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM user_profiles').fetchone()[0]==0
    verified=client.post('/api/auth/verify',json={'token':token})
    assert verified.status_code==200 and verified.json()['next']=='financials'
    assert 'HttpOnly' in verified.headers['set-cookie']
    with m.database() as db:
        assert db.execute('SELECT phone FROM user_profiles').fetchone()[0]=='+61 412 345 678'
    assert client.post('/api/auth/verify',json={'token':token}).status_code==400
    client.post('/api/auth/logout')
    assert client.get('/api/account/saved').status_code==401


def test_invalid_email_phone_and_redirect():
    c=TestClient(app)
    assert c.post('/api/auth/request-link',json={'email':'no-email'}).status_code==422
    assert c.post('/api/auth/request-link',json={'email':'x@example.com','phone':'abc'}).status_code==422
    for route in ['https://evil.example','//evil.example','login','admin?x=1','javascript:alert(1)']:
        assert auth.safe_next(route)=='overview'


def test_google_browser_binding_replay_and_verified_identity(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','test-secret')
    c=TestClient(app)
    started=c.get('/api/auth/google/start?next=financials',follow_redirects=False)
    query=parse_qs(urlparse(started.headers['location']).query)
    assert query['code_challenge_method']==['S256']
    state=query['state'][0]
    attacker=TestClient(app)
    assert 'error=' in attacker.get('/api/auth/google/callback',params={'state':state,'code':'code'},follow_redirects=False).headers['location']
    original=httpx.AsyncClient
    def upstream(request):
        if request.url.path=='/token':return httpx.Response(200,json={'access_token':'test-token'})
        return httpx.Response(200,json={'sub':'google-user','email':'google@gmail.com','email_verified':True})
    monkeypatch.setattr(auth.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(upstream),**kw))
    result=c.get('/api/auth/google/callback',params={'state':state,'code':'code'},follow_redirects=False)
    assert result.headers['location']=='/#financials'
    assert c.get('/api/account').json()['user']['email']=='google@gmail.com'
    assert 'error=' in c.get('/api/auth/google/callback',params={'state':state,'code':'code'},follow_redirects=False).headers['location']


def test_google_unverified_email_fails(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','test-secret')
    c=TestClient(app)
    start=c.get('/api/auth/google/start',follow_redirects=False)
    state=parse_qs(urlparse(start.headers['location']).query)['state'][0]
    original=httpx.AsyncClient
    monkeypatch.setattr(auth.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'access_token':'x','sub':'u','email':'fake@gmail.com','email_verified':False})),**kw))
    assert 'error=' in c.get('/api/auth/google/callback',params={'state':state,'code':'code'},follow_redirects=False).headers['location']
    assert c.get('/api/account').json()['user'] is None


def test_anonymous_session_check_does_not_open_database(monkeypatch):
    from types import SimpleNamespace
    from server import membership
    from fastapi import HTTPException
    import pytest
    def unexpected_database():
        raise AssertionError('Anonymous checks must not connect to the database')
    monkeypatch.setattr(membership, 'database', unexpected_database)
    request = SimpleNamespace(cookies={})
    assert membership.current_user(request) is None
    with pytest.raises(HTTPException) as error:
        membership.current_user(request, required=True)
    assert error.value.status_code == 401
