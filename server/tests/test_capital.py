import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from server import capital
from server.app import app


def row(cusip='123456789', value=100, shares=10, option='', unit='SH', name='Example Inc'):
    return dict(cusip=cusip, name=name, value=value, shares=shares, option=option, unit=unit, **{'class': 'COM'})


def table(value=100):
    return f'''<informationTable xmlns="urn:sec"><infoTable><nameOfIssuer>Example Inc</nameOfIssuer>
    <titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>{value}</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    </infoTable></informationTable>'''.encode()


def test_xml_units_and_aggregation_do_not_mix_options_or_principal():
    assert capital.parse_13f(table(123), '2026-08-14')[0]['value'] == 123
    assert capital.parse_13f(table(123), '2022-11-14')[0]['value'] == 123000
    combined = capital.aggregate([row(), row(), row(option='PUT'), row(unit='PRN')])
    assert len(combined) == 3
    assert combined[0]['value'] == 200 and combined[0]['shares'] == 20


def test_changes_are_share_changes_and_unknown_comparison_stays_unknown():
    old = capital.aggregate([row(value=100, shares=10), row(cusip='old', shares=3)])
    current = capital.aggregate([row(value=999, shares=10), row(cusip='new', shares=4)])
    records = {r['cusip']: r for r in capital.compare(current, old)}
    assert records['123456789']['change'] == 'unchanged'  # Price appreciation isn't buying.
    assert records['new']['change'] == 'new'
    assert records['old']['change'] == 'removed'
    assert records['old']['value'] == 0
    assert capital.compare(current, None)[0]['change'] == 'unknown'
    assert capital.compare(current, None)[0]['shareChange'] is None


def test_rejects_untrusted_urls_and_external_entities():
    for url in ['http://www.sec.gov/a', 'https://www.sec.gov.evil.test/a', 'https://127.0.0.1/a', 'https://user@www.sec.gov/a', 'https://www.sec.gov:444/a']:
        with pytest.raises(ValueError):
            capital.valid_url(url)
    with pytest.raises(Exception):
        capital.xml(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>')


def test_sec_entry_and_value_totals_are_checked():
    async def run():
        def handler(request):
            if request.url.path.endswith('index.json'):
                return httpx.Response(200, json={'directory': {'item': [{'name': 'table.xml'}]}})
            if request.url.path.endswith('primary_doc.xml'):
                return httpx.Response(200, content=b'<form><tableEntryTotal>1</tableEntryTotal><tableValueTotal>999</tableValueTotal></form>')
            return httpx.Response(200, content=table())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError, match='reconcile'):
                await capital.sec_filing(client, '1067983', {'accessionNumber': '0001193125-26-352200', 'filingDate': '2026-08-14'})
    asyncio.run(run())


def test_restatement_skips_superseded_base_and_new_holdings_are_added(monkeypatch):
    entries = [
        ('0000000001-26-000003', '2026-08-16', '2026-06-30', '13F-HR/A'),
        ('0000000001-26-000002', '2026-08-15', '2026-06-30', '13F-HR/A'),
        ('0000000001-26-000001', '2026-08-14', '2026-06-30', '13F-HR'),
        ('0000000001-26-000000', '2026-05-14', '2026-03-31', '13F-HR'),
    ]
    payload = {'filings': {'recent': {k: [v[i] for v in entries] for i, k in enumerate(['accessionNumber', 'filingDate', 'reportDate', 'form'])}}}
    payload['filings']['recent']['primaryDocument'] = ['primary_doc.xml'] * 4
    called = []
    async def fake_download(*args, **kwargs):
        return json.dumps(payload).encode()
    async def fake_filing(client, cik, filing):
        suffix = filing['accessionNumber'][-1]
        called.append(suffix)
        if suffix == '1':
            raise ValueError('Superseded bad base must never be parsed')
        rows = [row(cusip='additional')] if suffix == '3' else [row()]
        return rows, 'NEW HOLDINGS' if suffix == '3' else 'RESTATEMENT', {'id': suffix, 'date': filing['filingDate'], 'period': filing['reportDate']}
    monkeypatch.setattr(capital, 'download', fake_download)
    monkeypatch.setattr(capital, 'sec_filing', fake_filing)
    result = asyncio.run(capital.institution(None, capital.PROFILES[0]))
    assert called == ['3', '2', '0']
    assert result['totalValue'] == 200
    assert result['holdingsCount'] == 2
    assert result['previousReportDate'] == '2026-03-31'


def test_source_failure_keeps_last_success_and_throttles_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(capital, 'STORE', tmp_path)
    monkeypatch.setenv('SEC_USER_AGENT', 'Test test@example.com')
    monkeypatch.setattr(capital, 'acquire', lambda *args, **kwargs: 'owner')
    monkeypatch.setattr(capital, 'release', lambda *args: None)
    calls = []
    async def failed(*args):
        calls.append(1)
        raise ValueError('upstream unavailable')
    monkeypatch.setattr(capital, 'institution', failed)
    original = {'version': capital.VERSION, 'attempted': 0, 'checkedAt': '2026-11-01T00:00:00+00:00', 'rows': [row()], 'documents': []}
    capital.write(tmp_path / 'berkshire.json', original)
    result = asyncio.run(capital.load('berkshire'))
    assert result['stale'] and result['checkedAt'] == original['checkedAt']
    assert result['rows'] == original['rows']
    asyncio.run(capital.load('berkshire'))
    assert len(calls) == 1


def test_api_filters_pagination_and_unknown_profile(monkeypatch):
    async def fake_load(ident):
        return {'rows': [{**row(cusip=str(i), name='Apple' if i < 30 else 'Other'), 'change': 'increase' if i % 2 else 'new'} for i in range(40)], 'documents': []}
    monkeypatch.setattr(capital, 'load', fake_load)
    client = TestClient(app)
    response = client.get('/api/capital/berkshire?q=apple&category=increase&offset=10&limit=3')
    assert response.status_code == 200
    assert response.json()['filteredCount'] == 15
    assert len(response.json()['rows']) == 3
    assert response.json()['recordCount'] == 40
    assert client.get('/api/capital/not-listed').status_code == 404
    assert client.get('/api/capital/berkshire?limit=1000').status_code == 422
    assert client.get('/api/cron/capital').status_code == 401


def test_redirects_cannot_escape_allowlist():
    async def run():
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={'Location': 'http://169.254.169.254/'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await capital.download(client, 'https://www.sec.gov/file')
        assert len(calls) == 1
    asyncio.run(run())


def test_scheduled_checks_do_not_skip_due_to_download_time_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(capital, 'STORE', tmp_path)
    monkeypatch.setenv('SEC_USER_AGENT', 'Test test@example.com')
    monkeypatch.setattr(capital, 'acquire', lambda *args, **kwargs: 'owner')
    monkeypatch.setattr(capital, 'release', lambda *args: None)
    calls = []
    async def fresh(*args):
        calls.append(1)
        return {'rows': [row()], 'documents': []}
    monkeypatch.setattr(capital, 'institution', fresh)
    capital.write(tmp_path / 'berkshire.json', {'version': capital.VERSION, 'attempted': time.time() - capital.TTL + 30,
        'checkedAt': '2026-11-10T00:00:30+00:00', 'status': 'ready', 'stale': False, 'rows': [], 'documents': []})
    asyncio.run(capital.load('berkshire'))
    assert not calls
    asyncio.run(capital.load('berkshire', scheduled=True))
    assert len(calls) == 1
