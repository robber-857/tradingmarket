import json
import time
import pytest
from fastapi.testclient import TestClient
from server.app import app
from server import membership as m, billing_engine as engine, payment_providers as providers, payment_operations as ops
from server.billing_catalog import QuoteRequest, quote


def login(client, email):
    return client.post('/api/auth/verify',json={'token':m.issue_login(email)}).json()['user']['id']


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv('CLARORA_ADMIN_EMAILS','ops@example.invalid')
    monkeypatch.setenv('CLARORA_ADMIN_USER_IDS','')
    monkeypatch.setenv('BILLING_ADMIN_USER_IDS','')
    with TestClient(app) as client:
        login(client,'ops@example.invalid')
        yield client


@pytest.fixture
def enabled(monkeypatch):
    for key,value in {'BILLING_TEST_ENABLED':'1','STRIPE_TEST_SECRET_KEY':'sk_test_private_fixture',
                      'STRIPE_TEST_WEBHOOK_SECRET':'whsec_private_fixture','PAYPAL_SANDBOX_CLIENT_ID':'private_client',
                      'PAYPAL_SANDBOX_CLIENT_SECRET':'private_secret','PAYPAL_SANDBOX_WEBHOOK_ID':'private_webhook'}.items():
        monkeypatch.setenv(key,value)


def order(method='card',age=3600):
    with TestClient(app) as guest:
        uid=login(guest,'buyer-'+method+'@example.invalid')
    offer=quote(QuoteRequest(plan='research',currency='usd',period='week',method=method))
    result=engine.new_order(uid,offer,'ops-order-request-1')
    engine.update_order(result['id'],provider_id='cs_test_example' if method=='card' else 'PAYPAL_ORDER',status='pending',checkout_url='https://checkout.stripe.com/private-url')
    with m.database() as db:db.execute('UPDATE billing_orders SET created=? WHERE id=?',(time.time()-age,result['id']))
    return engine.get_order(result['id'])


def test_readiness_never_discloses_values_and_does_not_claim_verified(admin,enabled,monkeypatch):
    monkeypatch.setenv('STRIPE_TEST_PORTAL_CONFIGURATION','bpc_private_fixture')
    r=admin.get('/api/admin/billing/readiness')
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert 'private_' not in r.text
    data=r.json()
    assert all(data['channels'].values())
    assert not data['salesEnabled'] and not data['credentialsVerified'] and not data['webhookDeliveryVerified']
    monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_live_private_fixture')
    result=admin.get('/api/admin/billing/readiness').json()
    assert not result['channels']['card'] and not result['channels']['alipay']
    assert next(c for c in result['checks'] if c['key']=='STRIPE_TEST_SECRET_KEY')['state']=='invalid'


def test_missing_configuration_is_reported_without_channel_requests(admin,monkeypatch):
    for key in ['STRIPE_TEST_SECRET_KEY','STRIPE_TEST_WEBHOOK_SECRET','PAYPAL_SANDBOX_CLIENT_ID','PAYPAL_SANDBOX_CLIENT_SECRET','PAYPAL_SANDBOX_WEBHOOK_ID']:
        monkeypatch.setenv(key,'')
    monkeypatch.setenv('BILLING_TEST_ENABLED','0')
    data=admin.get('/api/admin/billing/readiness').json()
    assert not any(data['channels'].values())
    assert sum(c['state']=='missing' for c in data['checks'])>=5


def test_ordinary_and_anonymous_users_cannot_inspect_payment_operations():
    with TestClient(app) as client:
        assert client.get('/api/admin/billing/readiness').status_code==401
        login(client,'ordinary-ops@example.invalid')
        for route in ['readiness','orders']:
            assert client.get('/api/admin/billing/'+route).status_code==403
        assert client.post('/api/admin/billing/orders/unknown/reconcile',json={'reason':'investigate'}).status_code==403


def test_queue_filters_and_does_not_expose_checkout_urls(admin):
    old=order();order('paypal',age=0)
    result=admin.get('/api/admin/billing/orders')
    assert result.json()['total']==1 and result.json()['items'][0]['id']==old['id']
    assert 'private-url' not in result.text and 'checkout_url' not in result.text
    assert admin.get('/api/admin/billing/orders?min_age_minutes=0').json()['total']==2
    assert admin.get('/api/admin/billing/orders?offset=25').json()['items']==[]


def test_stripe_paid_reconciliation_only_reads_provider_and_is_idempotent(admin,enabled,monkeypatch):
    o=order();calls=[]
    async def stripe(method,path,*args):
        calls.append((method,path))
        assert method=='GET'
        return {'checkout/sessions/cs_test_example':{'id':'cs_test_example','mode':'payment','status':'complete',
                   'payment_status':'paid','client_reference_id':o['id'],'metadata':{'order_id':o['id']},'payment_intent':'pi_ops'},
                'payment_intents/pi_ops':{'id':'pi_ops','status':'succeeded','metadata':{'order_id':o['id']},'latest_charge':'ch_ops','amount_received':700,'currency':'usd'},
                'charges/ch_ops':{'paid':True,'payment_intent':'pi_ops','created':int(time.time()),'amount_refunded':0}}[path]
    monkeypatch.setattr(providers,'stripe',stripe)
    url='/api/admin/billing/orders/'+o['id']+'/reconcile'
    for _ in range(2):
        r=admin.post(url,json={'reason':'buyer reports delayed access'})
        assert r.status_code==200 and r.json()['status']=='paid'
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM billing_payments').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM grants').fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM admin_actions WHERE action='billing_reconcile'").fetchone()[0]==2
    assert len(calls)==6


def test_approved_paypal_reconcile_never_captures(admin,enabled,monkeypatch):
    o=order('paypal');calls=[]
    async def paypal(method,path,*args):
        calls.append((method,path))
        assert method=='GET'
        return {'id':'PAYPAL_ORDER','status':'APPROVED','purchase_units':[{'custom_id':o['id'],'amount':{'value':'7.00','currency_code':'USD'}}]}
    monkeypatch.setattr(providers,'paypal',paypal)
    result=admin.post('/api/admin/billing/orders/'+o['id']+'/reconcile',json={'reason':'check pending approval'})
    assert result.status_code==200 and result.json()['status']=='pending'
    with m.database() as db:assert db.execute('SELECT count(*) FROM grants').fetchone()[0]==0
    assert len(calls)==1


def test_failed_mismatched_check_audited_without_grant(admin,enabled,monkeypatch):
    o=order()
    async def stripe(*args):return {'client_reference_id':'another-order','metadata':{'order_id':'another-order'}}
    monkeypatch.setattr(providers,'stripe',stripe)
    result=admin.post('/api/admin/billing/orders/'+o['id']+'/reconcile',json={'reason':'inspect mismatch'})
    assert result.status_code==409
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM grants').fetchone()[0]==0
        detail=json.loads(db.execute("SELECT detail FROM admin_actions WHERE action='billing_reconcile'").fetchone()[0])
        assert detail['outcome']=='failed' and detail['errorStatus']==409


def test_missing_provider_id_cannot_be_forced_paid(admin,enabled):
    o=order();engine.update_order(o['id'],provider_id=None,status='creating')
    url='/api/admin/billing/orders/'+o['id']+'/reconcile'
    assert admin.post(url,json={'reason':'manual verify','status':'paid'}).status_code==422
    assert admin.post(url,json={'reason':'manual verify'}).status_code==409
    assert engine.get_order(o['id'])['status']=='creating'


def test_reconciliation_requires_test_switch_and_valid_note(admin,monkeypatch):
    o=order();monkeypatch.setenv('BILLING_TEST_ENABLED','0')
    url='/api/admin/billing/orders/'+o['id']+'/reconcile'
    assert admin.post(url,json={'reason':'   '}).status_code==422
    assert admin.post(url,json={'reason':'check request'}).status_code==503


def test_public_origin_check_remains_required(monkeypatch):
    monkeypatch.setenv('CLARORA_MODE','public')
    monkeypatch.setenv('CLARORA_PUBLIC_URL','https://clarora.example')
    monkeypatch.setenv('CLARORA_ADMIN_EMAILS','ops@example.invalid')
    with TestClient(app,base_url='https://clarora.example') as client:
        r=client.post('/api/auth/verify',json={'token':m.issue_login('ops@example.invalid')},headers={'Origin':'https://clarora.example'})
        assert r.status_code==200
        assert client.post('/api/admin/billing/orders/unknown/reconcile',json={'reason':'check status'},headers={'Origin':'https://other.example'}).status_code==403
