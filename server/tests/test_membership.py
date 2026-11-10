import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server.app import app
from server import membership as m, academy, news_ai
from server.billing_catalog import QuoteRequest, quote


def login(client, email='member@example.com'):
    token=m.issue_login(email)
    response=client.post('/api/auth/verify',json={'token':token})
    assert response.status_code==200
    return response.json()['user']['id']


def grant(user, plan='advanced', days=30):
    with m.database() as db:
        db.execute('INSERT INTO grants VALUES (?,?,?,?,?,?,0)',
                   ('paid-'+user,user,plan,time.time()-1,time.time()+days*86400,json.dumps(m.PLANS[plan]['limits'])))


def test_fallback_is_replayable_without_spending_quota():
    with TestClient(app) as client:
        uid=login(client)
        before=client.get('/api/account').json()['usage']
        assert m.reserve(uid,'basic-result','fingerprint','deep') is None
        result={'answer':{'text':'基础解读'},'chargeable':False,'conversationId':'d'*32}
        m.finish(uid,'basic-result',result)
        assert client.get('/api/account').json()['usage']==before
        assert m.reserve(uid,'basic-result','fingerprint','deep')==result
        m.check_conversation(uid,'d'*32)
        assert m.reserve(uid,'next-real-request','different','deep') is None


def test_http_fallback_replay_keeps_allowance(monkeypatch):
    calls=[]
    async def fallback(body):
        calls.append(True)
        return {'answer':{'text':'已确认的内容'},'outputMode':'partial','chargeable':False,'conversationId':'e'*32}
    monkeypatch.setattr(news_ai,'explain',fallback)
    with TestClient(app) as client:
        login(client)
        before=client.get('/api/account').json()['usage']
        body={'snapshot_id':'a'*24,'analysis_depth':'deep'}
        headers={'Idempotency-Key':'fallback-http-test'}
        first=client.post('/api/news/explain',json=body,headers=headers)
        second=client.post('/api/news/explain',json=body,headers=headers)
        assert first.status_code==second.status_code==200
        assert second.headers['x-clarora-replayed']=='true'
        assert len(calls)==1 and client.get('/api/account').json()['usage']==before


def test_magic_link_one_use_and_cookie_logout():
    with TestClient(app) as client:
        token=m.issue_login('person@example.com')
        r=client.post('/api/auth/verify',json={'token':token})
        assert 'HttpOnly' in r.headers['set-cookie']
        assert client.post('/api/auth/verify',json={'token':token}).status_code==400
        assert client.get('/api/account').json()['plan']=='free'
        client.post('/api/auth/logout')
        assert client.get('/api/account').json()['user'] is None


def test_saved_records_are_account_scoped():
    with TestClient(app) as a, TestClient(app) as b:
        login(a,'a@example.com');login(b,'b@example.com')
        data={'kind':'research','title':'Private study','payload':{'symbol':'AAPL'}}
        assert a.put('/api/account/saved/my-report',json=data).status_code==200
        assert b.get('/api/account/saved').json()['items']==[]
        b.delete('/api/account/saved/my-report')
        assert len(a.get('/api/account/saved').json()['items'])==1
        assert b.put('/api/account/saved/my-report',json={**data,'user_id':'someone'}).status_code==422


@pytest.mark.usefixtures('public_database')
def test_public_blocks_anonymous_ai_and_local_login_links(monkeypatch):
    monkeypatch.setenv('CLARORA_MODE','public')
    monkeypatch.setenv('CLARORA_PUBLIC_URL','https://clarora.example')
    monkeypatch.setenv('SMTP_HOST','')
    with TestClient(app,base_url='https://clarora.example') as client:
        assert client.post('/api/news/explain',json={}).status_code==403
        headers={'Origin':'https://clarora.example'}
        assert client.post('/api/news/explain',json={},headers=headers).status_code==401
        r=client.post('/api/auth/request-link',json={'email':'x@example.com'},headers=headers)
        assert r.status_code==503 and 'localLoginUrl' not in r.text
        assert client.post('/api/briefs/generate',headers=headers).status_code==403


def test_course_body_never_leaks_from_catalog_and_server_enforces(monkeypatch):
    monkeypatch.setattr(academy,'courses',lambda:[{'id':'premium','access':'premium','title':'Paid','body':'SECRET LESSON'}])
    with TestClient(app) as client:
        assert 'SECRET LESSON' not in client.get('/api/academy/courses').text
        assert client.get('/api/academy/courses/premium').status_code==403
        user=login(client)
        assert client.get('/api/academy/courses/premium').status_code==403
        grant(user)
        assert client.get('/api/academy/courses/premium').json()['body']=='SECRET LESSON'
        with m.database() as db:db.execute('UPDATE grants SET end=?',(time.time()-1,))
        assert client.get('/api/academy/courses/premium').status_code==403


def test_meter_atomic_limit_idempotency_and_failure_refund():
    with TestClient(app) as client:user=login(client)
    def reserve(i):
        try:m.reserve(user,str(i),'same','ai');return True
        except HTTPException as e:assert e.status_code==402;return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve,range(8)))==5
    with m.database() as db:key=db.execute('SELECT key FROM usage WHERE user_id=? LIMIT 1',(user,)).fetchone()[0]
    m.finish(user,key)
    assert m.reserve(user,'retry-new','same','ai') is None
    m.finish(user,'retry-new',{'answer':'ok'})
    assert m.reserve(user,'retry-new','same','ai')=={'answer':'ok'}
    with pytest.raises(HTTPException) as exc:m.reserve(user,'retry-new','changed','ai')
    assert exc.value.status_code==409


def test_deep_separate_and_sentiment_closed():
    with TestClient(app) as client:user=login(client)
    m.reserve(user,'deep-1','one','deep');m.finish(user,'deep-1',{'answer':'ok'})
    with pytest.raises(HTTPException):m.reserve(user,'deep-2','two','deep')
    assert m.reserve(user,'normal','normal','ai') is None
    with pytest.raises(HTTPException) as exc:m.reserve(user,'sentiment','s','sentiment')
    assert exc.value.status_code==503


def test_ai_route_meter_replay_ownership_and_failed_validation(monkeypatch):
    called=[]
    async def explain(body):
        called.append(m.DEPTH.get())
        return {'answer':{'text':'ok'},'conversationId':'a'*32}
    monkeypatch.setattr(news_ai,'explain',explain)
    with TestClient(app) as a, TestClient(app) as b:
        login(a,'a@example.com');login(b,'b@example.com')
        headers={'Idempotency-Key':'analysis-request-1'}
        body={'snapshot_id':'a'*24,'analysis_depth':'deep'}
        assert a.post('/api/news/explain',json=body,headers=headers).status_code==200
        r=a.post('/api/news/explain',json=body,headers=headers)
        assert r.headers['x-clarora-replayed']=='true' and called==['deep']
        assert b.post('/api/news/explain',json={**body,'conversation_id':'a'*32}).status_code==403
        assert a.get('/api/account').json()['usage']['deep']['used']==1
        bad=a.post('/api/news/explain',json={'snapshot_id':'invalid'},headers={'Idempotency-Key':'invalid-request-1'})
        assert bad.status_code==422
        assert a.get('/api/account').json()['usage']['ai']['used']==0


@pytest.mark.parametrize('currency,method,expected', [('cny','alipay',12900),('aud','card',2900),('usd','apple_pay',1900)])
def test_currency_quotes_server_owned(currency,method,expected):
    data=quote(QuoteRequest(plan='research',currency=currency,method=method))
    assert data['amountMinor']==expected
    assert data['salesEnabled'] is False
    assert data['renewal']==('manual' if method=='alipay' else 'automatic')


def test_week_not_month_and_invalid_channels():
    data=quote(QuoteRequest(plan='research',currency='usd',method='card',period='week'))
    assert data['amountMinor']==700 and data['renewal']=='manual' and data['limits']['deep']==3
    with pytest.raises(HTTPException):quote(QuoteRequest(plan='expert',currency='usd',method='card',period='week'))
    with pytest.raises(HTTPException):quote(QuoteRequest(plan='research',currency='cny',method='card'))


def test_cross_origin_mutation_rejected():
    with TestClient(app) as client:
        assert client.post('/api/auth/request-link',json={'email':'a@b.com'},headers={'Origin':'https://evil.example'}).status_code==403
