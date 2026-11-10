import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import hmac
import json
import time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server.app import app
from server import membership as m, billing as b, billing_engine as e, payment_providers as p
from server.billing_catalog import QuoteRequest,quote


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('BILLING_TEST_ENABLED','1')
    monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_test_fixture')
    monkeypatch.setenv('STRIPE_TEST_WEBHOOK_SECRET','whsec_fixture')
    monkeypatch.setenv('PAYPAL_SANDBOX_CLIENT_ID','fixture')
    monkeypatch.setenv('PAYPAL_SANDBOX_CLIENT_SECRET','fixture')
    monkeypatch.setenv('PAYPAL_SANDBOX_WEBHOOK_ID','fixture')


def login(client,email='billing@example.invalid'):
    response=client.post('/api/auth/verify',json={'token':m.issue_login(email)})
    assert response.status_code==200
    return response.json()['user']['id']


def order(user,method='card',period='month',plan='research'):
    offer=quote(QuoteRequest(plan=plan,currency='cny' if method=='alipay' else 'usd',method=method,period=period))
    return e.new_order(user,offer,'request-key-12345')


def paid(user,method='card',plan='research',stamp=None):
    o=order(user,method,plan=plan);q=json.loads(o['quote'])
    pid=e.record_payment(o,'pi_fixture' if method!='paypal' else 'CAPTURE',q['amountMinor'],q['currency'],stamp or time.time())
    return o,pid


def signed(event,stamp=None):
    raw=json.dumps(event).encode();stamp=stamp or int(time.time())
    sig=hmac.new(b'whsec_fixture',str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return raw,{'Stripe-Signature':f't={stamp},v1={sig}','Content-Type':'application/json'}


def test_default_off_and_live_key_rejected(monkeypatch,enabled):
    monkeypatch.setenv('BILLING_TEST_ENABLED','0')
    assert not p.availability()['stripe']
    monkeypatch.setenv('BILLING_TEST_ENABLED','1')
    monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_live_not_allowed')
    with pytest.raises(HTTPException):p.require('stripe')


def test_order_request_id_and_active_purchase_guard():
    with TestClient(app) as client:user=login(client)
    o=order(user)
    assert order(user)['id']==o['id']
    e.record_payment(o,'pi_one',1900,'usd',time.time())
    with pytest.raises(HTTPException):e.new_order(user,quote(QuoteRequest(plan='research',currency='usd',method='card')),'different-key')


def test_payment_grant_idempotent_and_mismatch():
    with TestClient(app) as client:user=login(client)
    o=order(user)
    with pytest.raises(HTTPException):e.record_payment(o,'pi_bad',1,'usd',time.time())
    with pytest.raises(HTTPException):e.record_payment(o,'pi_bad',1900,'aud',time.time())
    def record(_):return e.record_payment(o,'pi_paid',1900,'usd',time.time())
    with ThreadPoolExecutor(max_workers=5) as pool:assert len(set(pool.map(record,range(5))))==1
    with m.database() as db:assert db.execute('SELECT count(*) FROM grants').fetchone()[0]==1


def test_calendar_month_not_thirty_days():
    jan=datetime(2028,1,31,12,tzinfo=timezone.utc).timestamp()
    assert datetime.fromtimestamp(e.next_month(jan),timezone.utc)==datetime(2028,2,29,12,tzinfo=timezone.utc)


def test_refund_freeze_reject_restore():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user)
        rf=client.post('/api/billing/payments/'+pid+'/refund-request',json={'reason':'测试退款申请'})
        assert rf.status_code==200
        assert client.get('/api/account').json()['plan']=='free'
        assert e.request_refund(user,pid,'重试')['id']==rf.json()['id']
        e.review(rf.json()['id'],'admin',False,'测试拒绝恢复')
        assert client.get('/api/account').json()['plan']=='research'


@pytest.mark.parametrize('kind',['ai','deep','course','pending','expired'])
def test_used_or_old_payment_not_refundable(kind):
    with TestClient(app) as client:user=login(client)
    o,pid=paid(user,plan='advanced',stamp=time.time()-8*86400 if kind=='expired' else None)
    grant='test:'+pid
    if kind in ('ai','deep','pending'):
        m.reserve(user,'unique-request','fingerprint','deep' if kind=='deep' else 'ai')
        if kind!='pending':m.finish(user,'unique-request',{'answer':'done'})
    if kind=='course':
        with m.database() as db:db.execute('INSERT INTO benefit_reads VALUES (?,?,?,?)',(user,grant,'premium',time.time()))
    with pytest.raises(HTTPException) as exc:e.request_refund(user,pid,'退款原因')
    assert exc.value.status_code==409


def test_failed_ai_and_free_course_do_not_block_refund():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user,plan='advanced')
        assert client.get('/api/academy/courses/l1').status_code==200
        m.reserve(user,'request1','f','ai');m.finish(user,'request1')
        assert e.request_refund(user,pid,'测试退款')['status']=='requested'


def test_premium_course_read_records_usage():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user,plan='advanced')
        assert client.get('/api/academy/courses/premium-research-journal').status_code==200
        assert client.post('/api/billing/payments/'+pid+'/refund-request',json={'reason':'测试申请'}).status_code==409


def test_full_refund_revokes_and_late_payment_does_not_restore():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user)
        rf=e.request_refund(user,pid,'测试原因');e.review(rf['id'],'admin',True,'批准')
        e.refund_result(rf['id'],'re_test','succeeded',1900,'usd')
        e.record_payment(o,'pi_fixture',1900,'usd',time.time())
        assert client.get('/api/account').json()['plan']=='free'
        assert e.list_account(user)['payments'][0]['state']=='refunded'


def test_owner_and_admin_isolation(enabled):
    with TestClient(app) as a,TestClient(app) as other:
        user=login(a);login(other,'other@example.invalid');o,pid=paid(user)
        assert other.get('/api/billing/account').json()['payments']==[]
        assert other.post('/api/billing/payments/'+pid+'/refund-request',json={'reason':'不允许'}).status_code==404
        assert a.get('/api/billing/admin/refunds').status_code==403
        assert other.post('/api/billing/orders/'+o['id']+'/refresh').status_code==404


def test_stripe_signature_timestamp_live_and_no_origin(enabled,monkeypatch):
    event={'id':'evt_test','type':'ignored','livemode':False,'data':{'object':{}}}
    raw,headers=signed(event)
    assert p.verify_stripe(raw,headers['Stripe-Signature'])['id']=='evt_test'
    with pytest.raises(HTTPException):p.verify_stripe(raw+b' ',headers['Stripe-Signature'])
    old,old_headers=signed(event,int(time.time())-600)
    with pytest.raises(HTTPException):p.verify_stripe(old,old_headers['Stripe-Signature'])
    live,live_headers=signed({**event,'livemode':True})
    with pytest.raises(HTTPException):p.verify_stripe(live,live_headers['Stripe-Signature'])
    monkeypatch.setenv('CLARORA_MODE','public');monkeypatch.setenv('CLARORA_PUBLIC_URL','https://clarora.example')
    with TestClient(app,base_url='https://clarora.example') as client:
        assert client.post('/api/billing/webhooks/stripe',content=raw,headers=headers).status_code==200
        assert client.post('/api/billing/webhooks/stripe',content=raw).status_code==400
        assert client.post('/api/auth/logout').status_code==403


def test_checkout_server_price_and_alipay_one_off(enabled,monkeypatch):
    calls=[]
    async def stripe(method,path,data=None,key=None):
        calls.append((path,data,key))
        return {'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/test_fixture'}
    monkeypatch.setattr(p,'stripe',stripe)
    with TestClient(app) as client:
        login(client)
        body={'plan':'research','currency':'cny','method':'alipay','period':'month','request_key':'unique-checkout-key'}
        r=client.post('/api/billing/checkout',json=body)
        assert r.status_code==200
        assert calls[0][1]['mode']=='payment' and calls[0][1]['line_items[0][price_data][unit_amount]']=='12900'
        assert client.post('/api/billing/checkout',json=body).status_code==200 and len(calls)==1
        assert client.get('/api/account').json()['plan']=='free'
        assert client.post('/api/billing/checkout',json={**body,'amount':1}).status_code==422


def test_stripe_subscription_renewal_failed_and_duplicate(enabled,monkeypatch):
    with TestClient(app) as client:user=login(client)
    o=order(user);now=int(time.time());periods={'in_first':(now-3600,now+86400),'in_next':(now+86400,now+31*86400)}
    async def stripe(method,path,data=None,key=None):
        if path=='subscriptions/sub_fixture':return {'id':'sub_fixture','metadata':{'order_id':o['id']},'status':'active','customer':'cus_test','cancel_at_period_end':False,
            'items':{'data':[{'quantity':1,'price':{'unit_amount':1900,'currency':'usd','recurring':{'interval':'month'}}}]}}
        ident=path.split('/')[-1];a,z=periods.get(ident,periods['in_next'])
        return {'id':ident,'subscription':'sub_fixture','status':'open' if ident=='in_failed' else 'paid','paid':ident!='in_failed',
            'amount_paid':1900,'total':1900,'currency':'usd','status_transitions':{'paid_at':now},'lines':{'data':[{'period':{'start':a,'end':z},'proration':False}]}}
    monkeypatch.setattr(p,'stripe',stripe)
    asyncio.run(b.stripe_invoice('in_first'));asyncio.run(b.stripe_invoice('in_failed'))
    asyncio.run(b.stripe_invoice('in_next'));asyncio.run(b.stripe_invoice('in_first'))
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM grants').fetchone()[0]==2
        assert m.entitlement(db,user,now+2*86400)['period'].startswith('test:pay_')
    assert len(e.list_account(user)['payments'])==2


def test_cancel_preserves_paid_grant(enabled,monkeypatch):
    async def stripe(*args):return {'status':'active','cancel_at_period_end':True}
    monkeypatch.setattr(p,'stripe',stripe)
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user)
        e.update_order(o['id'],subscription_id='sub_test',subscription_status='active')
        assert client.post('/api/billing/orders/'+o['id']+'/cancel-renewal').status_code==200
        assert client.get('/api/account').json()['plan']=='research'


def test_refund_provider_flow_idempotent(enabled,monkeypatch):
    posts=[]
    async def stripe(method,path,data=None,key=None):
        if method=='POST':posts.append(key)
        return {'id':'re_fixture','payment_intent':'pi_fixture','status':'succeeded','amount':1900,'currency':'usd'}
    monkeypatch.setattr(p,'stripe',stripe)
    with TestClient(app) as client:
        user=login(client);monkeypatch.setenv('BILLING_ADMIN_USER_IDS',user)
        o,pid=paid(user);rf=e.request_refund(user,pid,'测试申请')
        for _ in range(2):assert client.post('/api/billing/admin/refunds/'+rf['id']+'/review',json={'approve':True,'note':'测试批准'}).status_code==200
        assert len(posts)==1
        assert client.get('/api/account').json()['plan']=='free'


def test_paypal_capture_authoritative_amount_and_grant(enabled,monkeypatch):
    with TestClient(app) as client:user=login(client)
    o=order(user,'paypal');e.update_order(o['id'],provider_id='PPORDER');o=e.get_order(o['id'])
    calls=[];captured=False
    async def paypal(method,path,data=None,key=None):
        nonlocal captured
        calls.append(path)
        if path.endswith('/capture'):captured=True;return {}
        if '/captures/' in path:return {'id':'CAPTURE','status':'COMPLETED','amount':{'value':'19.00','currency_code':'USD'},'create_time':datetime.now(timezone.utc).isoformat()}
        return {'id':'PPORDER','status':'COMPLETED' if captured else 'APPROVED','purchase_units':[{'custom_id':o['id'],'amount':{'value':'19.00','currency_code':'USD'},'payments':{'captures':[{'id':'CAPTURE'}] if captured else []}}]}
    monkeypatch.setattr(p,'paypal',paypal)
    asyncio.run(b.paypal_order(o,True));asyncio.run(b.paypal_order(o,True))
    assert calls.count('/v2/checkout/orders/PPORDER/capture')==1
    assert len(e.list_account(user)['payments'])==1


def test_refund_cannot_match_different_payment(enabled,monkeypatch):
    async def stripe(*args):return {'id':'re_fixture','payment_intent':'pi_someone_else','status':'succeeded','amount':1900,'currency':'usd'}
    monkeypatch.setattr(p,'stripe',stripe)
    with TestClient(app) as client:user=login(client)
    o,pid=paid(user);rf=e.request_refund(user,pid,'测试原因')
    with m.database() as db:payment=dict(db.execute('SELECT * FROM billing_payments WHERE id=?',(pid,)).fetchone())
    with pytest.raises(HTTPException):asyncio.run(b.sync_refund({**rf,'provider_id':'re_fixture'},payment))


def test_webhook_duplicate_does_not_repeat_provider(enabled,monkeypatch):
    calls=[]
    async def stripe(method,path,data=None,key=None):calls.append(path);raise AssertionError('Unknown event must not fetch provider')
    monkeypatch.setattr(p,'stripe',stripe)
    event={'id':'evt_dedup','type':'unrelated','livemode':False,'data':{'object':{}}}
    raw,headers=signed(event)
    with TestClient(app) as client:
        for _ in range(2):assert client.post('/api/billing/webhooks/stripe',content=raw,headers=headers).status_code==200
    with m.database() as db:assert db.execute('SELECT count(*) FROM billing_events').fetchone()[0]==1


def test_external_partial_refund_holds_for_review():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user)
        b.external_refund('stripe','pi_fixture',100)
        assert client.get('/api/account').json()['plan']=='free'
        assert e.list_account(user)['payments'][0]['state']=='partial_refund_review'


def test_signed_async_checkout_only_grants_after_confirmed_payment(enabled,monkeypatch):
    with TestClient(app) as client:
        user=login(client);o=order(user,'alipay');q=json.loads(o['quote'])
        successful=False
        async def stripe(method,path,data=None,key=None):
            if path.startswith('checkout/sessions/'):
                return {'id':'cs_test_async','metadata':{'order_id':o['id']},'client_reference_id':o['id'],'mode':'payment',
                        'status':'complete','payment_status':'paid' if successful else 'unpaid','payment_intent':'pi_async'}
            if path.startswith('payment_intents/'):
                return {'id':'pi_async','status':'succeeded','metadata':{'order_id':o['id']},'latest_charge':'ch_async','amount_received':q['amountMinor'],'currency':'cny'}
            return {'id':'ch_async','paid':True,'payment_intent':'pi_async','created':int(time.time()),'amount_refunded':0}
        monkeypatch.setattr(p,'stripe',stripe)
        event={'id':'evt_pending','type':'checkout.session.completed','livemode':False,'data':{'object':{'id':'cs_test_async'}}}
        raw,headers=signed(event)
        assert client.post('/api/billing/webhooks/stripe',content=raw,headers=headers).status_code==200
        assert client.get('/api/account').json()['plan']=='free'
        successful=True
        raw,headers=signed({**event,'id':'evt_paid','type':'checkout.session.async_payment_succeeded'})
        assert client.post('/api/billing/webhooks/stripe',content=raw,headers=headers).status_code==200
        assert client.get('/api/account').json()['plan']=='research'
        assert client.post('/api/billing/webhooks/stripe',content=raw,headers=headers).status_code==200
        assert len(e.list_account(user)['payments'])==1


def test_renewal_refund_checks_new_period_not_previous_usage():
    with TestClient(app) as client:user=login(client)
    o=order(user);now=time.time()
    first=e.record_payment(o,'in_old',1900,'usd',now-3600,now-3600,now+3600)
    m.reserve(user,'old-use','f','ai');m.finish(user,'old-use',{'answer':'used'})
    next_id=e.record_payment(o,'in_new',1900,'usd',now,now+3600,now+30*86400)
    assert e.request_refund(user,next_id,'仅退新周期')['status']=='requested'
    with pytest.raises(HTTPException):e.request_refund(user,first,'上周期已使用')


def test_failed_refund_remains_held_until_admin_restores():
    with TestClient(app) as client:
        user=login(client);o,pid=paid(user);rf=e.request_refund(user,pid,'申请退款')
        e.review(rf['id'],'admin',True,'审核通过')
        e.refund_result(rf['id'],'re_failed','failed',1900,'usd')
        assert client.get('/api/account').json()['plan']=='free'
        e.review(rf['id'],'admin',False,'核对失败，恢复权益')
        assert client.get('/api/account').json()['plan']=='research'


def test_paypal_refund_matches_capture_and_revokes(enabled,monkeypatch):
    async def paypal(method,path,data=None,key=None):
        return {'id':'RFTEST','status':'COMPLETED','amount':{'value':'19.00','currency_code':'USD'},
                'links':[{'rel':'up','href':'https://api-m.sandbox.paypal.com/v2/payments/captures/CAPTURE'}]}
    monkeypatch.setattr(p,'paypal',paypal)
    with TestClient(app) as client:
        user=login(client);monkeypatch.setenv('BILLING_ADMIN_USER_IDS',user)
        o,pid=paid(user,'paypal');rf=e.request_refund(user,pid,'测试退款')
        response=client.post('/api/billing/admin/refunds/'+rf['id']+'/review',json={'approve':True,'note':'测试批准'})
        assert response.status_code==200
        assert client.get('/api/account').json()['plan']=='free'
        assert e.list_account(user)['payments'][0]['state']=='refunded'
