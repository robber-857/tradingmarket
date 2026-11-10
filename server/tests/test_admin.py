import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from server.app import app
from server import membership as m


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv('CLARORA_ADMIN_EMAILS', 'owner@example.com')
    monkeypatch.setenv('CLARORA_ADMIN_USER_IDS', '')
    with TestClient(app) as client:
        login(client, 'owner@example.com')
        yield client


def login(client, email):
    return client.post('/api/auth/verify', json={'token': m.issue_login(email)}).json()


def body(**kwargs):
    return {'email': 'guest@example.com', 'plan': 'advanced', 'days': 30,
            'reason': 'Invited for research', 'request_key': 'manual-grant-key-123', **kwargs}


def test_admin_read_and_write_denied_without_role():
    with TestClient(app) as client:
        assert client.get('/api/admin/users').status_code == 401
        login(client, 'ordinary@example.com')
        assert client.get('/api/admin/users').status_code == 403
        assert client.get('/api/admin/users/missing').status_code == 403
        assert client.post('/api/admin/users', json=body()).status_code == 403
        assert client.post('/api/admin/grants/missing/revoke', json={'reason': 'test revoke'}).status_code == 403


def test_manual_provision_login_course_access_and_audit(admin):
    result = admin.post('/api/admin/users', json=body())
    assert result.status_code == 200
    uid = result.json()['userId']
    with TestClient(app) as guest:
        account = login(guest, 'guest@example.com')
        assert account['plan'] == 'advanced' and account['allCourses']
        assert not account['isAdmin'] and account['usage']['deep']['limit'] == 40
        assert guest.get('/api/admin/users').status_code == 403
        assert guest.get('/api/academy/courses/premium-research-journal').status_code == 200
    detail = admin.get('/api/admin/users/'+uid).json()
    assert detail['grants'][0]['manual'] == 1
    assert {a['action'] for a in detail['actions']} == {'create_account', 'grant_membership'}
    assert admin.get('/api/admin/users').headers['cache-control'] == 'no-store'
    assert admin.get('/api/admin/users?q=guest').json()['total'] == 1


def test_idempotent_requests_and_payload_conflicts(admin):
    first = admin.post('/api/admin/users', json=body()).json()
    assert admin.post('/api/admin/users', json=body()).json() == first
    assert admin.post('/api/admin/users', json=body(days=90)).status_code == 409
    assert admin.post('/api/admin/users', json=body(request_key='different-key-12345')).status_code == 409
    detail = admin.get('/api/admin/users/'+first['userId']).json()
    assert len(detail['grants']) == 1 and len(detail['actions']) == 2


def test_revoke_removes_course_permission_preserves_saved_data(admin):
    provision = admin.post('/api/admin/users', json=body()).json()
    with TestClient(app) as guest:
        login(guest, 'guest@example.com')
        assert guest.put('/api/account/saved/report', json={'kind': 'research', 'title': 'Study', 'payload': {}}).status_code == 200
        endpoint = '/api/admin/grants/'+provision['grantId']+'/revoke'
        assert admin.post(endpoint, json={'reason': 'End of trial'}).status_code == 200
        assert admin.post(endpoint, json={'reason': 'End of trial'}).status_code == 200
        assert guest.get('/api/account').json()['plan'] == 'free'
        assert guest.get('/api/academy/courses/premium-research-journal').status_code == 403
        assert len(guest.get('/api/account/saved').json()['items']) == 1
    detail = admin.get('/api/admin/users/'+provision['userId']).json()
    assert len([a for a in detail['actions'] if a['action']=='revoke_membership']) == 1


def test_expiry_and_free_provision_does_not_reset_grants(admin):
    result = admin.post('/api/admin/users', json=body(days=7)).json()
    free = admin.post('/api/admin/users', json=body(plan='free', request_key='free-account-key-123')).json()
    assert not free['created'] and free['grantId'] is None
    with TestClient(app) as guest:
        assert login(guest, 'guest@example.com')['plan'] == 'advanced'
        with m.database() as db:
            db.execute('UPDATE grants SET end=? WHERE id=?', (time.time()-1, result['grantId']))
        assert guest.get('/api/account').json()['plan'] == 'free'


def test_payment_grants_cannot_be_revoked_or_masked(admin):
    with TestClient(app) as guest:
        uid = login(guest, 'guest@example.com')['user']['id']
    with m.database() as db:
        db.execute('INSERT INTO grants VALUES (?,?,?,?,?,?,0)',
                   ('payment-grant', uid, 'research', time.time()-1, time.time()+86400, json.dumps(m.PLANS['research']['limits'])))
    assert admin.post('/api/admin/grants/payment-grant/revoke', json={'reason': 'Attempt revoke'}).status_code == 404
    assert admin.post('/api/admin/users', json=body()).status_code == 409
    with m.database() as db:
        db.execute('UPDATE grants SET revoked=2 WHERE id=?', ('payment-grant',))
    assert admin.post('/api/admin/users', json=body()).status_code == 409


@pytest.mark.parametrize('change', [{'days': 0}, {'days': 367}, {'days': 1.5}, {'plan': 'admin'},
                                     {'isAdmin': True}, {'limits': {'deep': 999}}, {'reason': '   '}, {'email': 'invalid'}])
def test_invalid_and_privilege_escalating_payloads(admin, change):
    assert admin.post('/api/admin/users', json=body(**change)).status_code == 422


def test_concurrent_duplicate_provision_only_one_grant(admin):
    def send(_):
        return admin.post('/api/admin/users', json=body())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()['grantId'] for r in results}) == 1
    with m.database() as db:
        assert db.execute('SELECT count(*) FROM grants').fetchone()[0] == 1


@pytest.mark.usefixtures('public_database')
def test_public_origin_and_admin_access(monkeypatch):
    monkeypatch.setenv('CLARORA_MODE', 'public')
    monkeypatch.setenv('CLARORA_PUBLIC_URL', 'https://clarora.example')
    monkeypatch.setenv('CLARORA_ADMIN_EMAILS', 'owner@example.com')
    with TestClient(app, base_url='https://clarora.example') as client:
        response = client.post('/api/auth/verify', json={'token': m.issue_login('owner@example.com')},
                               headers={'Origin': 'https://clarora.example'})
        assert response.json()['isAdmin']
        assert client.post('/api/admin/users', json=body()).status_code == 403
        assert client.post('/api/admin/users', json=body(), headers={'Origin': 'https://attacker.example'}).status_code == 403
        assert client.post('/api/admin/users', json=body(), headers={'Origin': 'https://clarora.example'}).status_code == 200


def test_admin_role_revocation_applies_to_existing_session(admin, monkeypatch):
    assert admin.get('/api/account').json()['isAdmin']
    monkeypatch.setenv('CLARORA_ADMIN_EMAILS', '')
    assert admin.get('/api/admin/users').status_code == 403
    assert not admin.get('/api/account').json()['isAdmin']
