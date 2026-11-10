"""Synthetic fixtures exercise units, vintages, clocks and evidence boundaries."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server import macro, macro_ai, narrative
from server.app import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(macro, 'CACHE', tmp_path)
    monkeypatch.setattr(macro, 'SNAPSHOTS', tmp_path)
    monkeypatch.setattr(macro, 'now', lambda: datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
    macro_ai.SESSIONS.clear(); macro_ai.ACTIVE.clear(); macro_ai.CALLS.clear()


def sample(**kwargs):
    e = macro.event('CPI', 'CPI 环比', '2026-10-14T12:30:00+00:00', '2026-09', 'BLS', 'https://www.bls.gov/cpi/')
    e.update(kwargs)
    return e


@pytest.mark.parametrize('raw,unit,n', [('0%', '%', 0), ('-0.2%', '%', -.2), ('178K', '人', 178000), ('-1.2M', '人', -1200000), ('165,000', '人', 165000), ('3.75–4%', '%', None), ('15K', '%', None), ('1%', '人', None)])
def test_scalar_units(raw, unit, n):
    assert macro.metric(raw, unit)['value'] == n


@pytest.mark.parametrize('raw', [None, '', '-', 'N/A', '.', False])
def test_missing_not_zero(raw):
    assert macro.metric(raw, '%') is None


def test_surprise_percentage_points_not_percent(tmp_path):
    e = macro.finalize(sample(actual=macro.metric('0.3%', '%'), forecast=macro.metric('0%', '%')))
    assert e['status'] == 'released'
    assert e['surprise']['value'] == .3
    assert e['surprise']['unit'] == '百分点'
    assert macro.load_snapshot(e['snapshotId']) == e


def test_future_actual_is_hidden():
    e = macro.finalize(sample(releaseAt='2026-11-10T13:30:00Z', actual=macro.metric('0.4%', '%'), forecast=macro.metric('0.3%', '%')))
    assert e['actual'] is None and e['surprise'] is None and e['status'] == 'upcoming'


def test_past_missing_actual_not_released():
    assert macro.finalize(sample())['status'] == 'pending'


def test_te_consensus_revision_and_date_precision():
    rows = [{'Country': 'United States', 'CalendarId': '12', 'Date': '2026-10-14T12:30:00',
             'Event': 'Inflation Rate MoM (Sep)', 'Reference': 'Sep', 'DateSpan': '1',
             'Previous': '0.2%', 'Revised': '0.1%', 'Forecast': '', 'TEForecast': '0.4%', 'Actual': '0.3%',
             'SourceURL': 'javascript:alert(1)'}]
    e = macro.normalize_te(rows)[0]
    assert e['forecast'] is None
    assert e['previous']['value'] == .2 and e['previousBeforeRevision']['value'] == .1
    assert e['timePrecision'] == 'estimated'
    assert e['sourceUrl'] == macro.TE_DOCS
    assert e['releaseAt'].endswith('+00:00')
    rows[0]['Country'] = 'Canada'
    assert macro.normalize_te(rows) == []


def test_no_core_pce_quarter_or_fomc_minutes_mix():
    rows = [{'Country': 'United States', 'Event': title} for title in ('Core PCE Price Index QoQ', 'FOMC Minutes', 'ADP Employment Change')]
    assert macro.normalize_te(rows) == []


def test_bls_schedule_dst_and_utc():
    ics = 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Consumer Price Index\nDTSTART;TZID=America/New_York:20261014T083000\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:Employment Situation\nDTSTART:20261106T133000Z\nEND:VEVENT'
    rows = macro.parse_bls_schedule(ics)
    assert rows[0]['releaseAt'] == '2026-10-14T12:30:00+00:00'
    assert rows[1]['releaseAt'] == '2026-11-06T13:30:00+00:00'


def test_bls_pdf_dates_and_reference():
    text = '8:30 a.m. (ET) Friday, November 6, 2026 THE EMPLOYMENT SITUATION — OCTOBER 2026 The Employment Situation for November 2026 is scheduled to be published on Friday, December\n4, 2026, at 8:30 a.m. (ET).'
    rows = macro.parse_bls_pdf(text, 'https://www.dol.gov/newsroom/economicdata/empsit_11062026.pdf', 'NFP')
    assert rows[0]['reference'] == '2026-10'
    assert rows[1]['releaseAt'] == '2026-12-04T13:30:00+00:00'
    assert all(e['actual'] is None for e in rows)


def test_bls_period_math_missing_months():
    points = [{'year': '2026', 'period': 'M10', 'value': '102'}, {'year': '2026', 'period': 'M09', 'value': '100'},
              {'year': '2026', 'period': 'M07', 'value': '95'}, {'year': '2026', 'period': 'M13', 'value': '999'}]
    payload = {'status': 'REQUEST_SUCCEEDED', 'Results': {'series': [{'seriesID': 'CES0000000001', 'data': points}]}}
    row = macro.bls_observations(payload)[0]
    assert row['actual']['value'] == 2000
    assert row['previous'] is None  # Never bridge the missing August.
    assert row['releaseAt'] is None
    assert '不是首发值' in row['valueBasis']


def test_bea_release_extracts_price_not_spending():
    html = '<div class="field--name-field-release-date">8:30 a.m. EDT, Thursday, October 29, 2026</div><h1>Personal Income and Outlays, September 2026</h1><table><caption>Percent change from preceding month</caption><tr><td>Current-dollar PCE</td><td>9</td><td>8</td></tr><tr><td>PCE price index</td><td>0.2</td><td>0.3</td></tr><tr><td>PCE price index excluding food and energy</td><td>0.1</td><td>0.2</td></tr></table>'
    rows = macro.parse_bea_release(html, macro.BEA_PCE)
    assert len(rows) == 2 and rows[0]['actual']['value'] == .3
    assert rows[0]['releaseAt'] == '2026-10-29T12:30:00+00:00'


def test_fed_range_fraction_and_change_clause():
    assert macro.parse_fed_rate('target range for the federal funds rate by 1/4 percentage point to 3-3/4 to 4 percent')['lower'] == 3.75
    assert macro.parse_fed_rate('target range for the federal funds rate at 0 to 1/4 percent')['upper'] == .25
    assert macro.parse_fed_rate('target range for the federal funds rate at 3.75 to 4 percent')['lower'] == 3.75
    assert macro.parse_fed_rate('effective federal funds rate at 4 percent') is None


def test_fed_date_only_not_invented_time():
    html = '<div class="panel"><div class="panel-heading">2026 FOMC Meetings</div><div class="fomc-meeting"><div class="fomc-meeting__month">December</div><div class="fomc-meeting__date">8-9*</div></div></div>'
    row = macro.parse_fed_schedule(html)[0]
    assert row['timePrecision'] == 'date-only'


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://bls.gov.evil.test/x', 'https://x@bls.gov/x', 'http://127.0.0.1/x'])
def test_source_urls_safe(url):
    assert macro.safe_url(url, 'fallback') == 'fallback'


def test_cache_stale_and_expired(tmp_path, monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(macro.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(503)), **kw))
    path = tmp_path / 'test.json'
    path.write_text(json.dumps({'body': 'previous valid response', 'retrievedAt': macro.iso(macro.now()-timedelta(hours=2))}))
    assert asyncio.run(macro.cached('test', macro.BEA_SCHEDULE))[2] is True
    path.write_text(json.dumps({'body': 'too old', 'retrievedAt': macro.iso(macro.now()-timedelta(days=8))}))
    with pytest.raises(macro.MacroError): asyncio.run(macro.cached('test', macro.BEA_SCHEDULE))


def test_date_range_and_snapshot_validation():
    with TestClient(app) as client:
        assert client.get('/api/macro/calendar?start=2026-12-01&end=2026-11-01').status_code == 422
        assert client.get('/api/macro/calendar?start=2026-01-01&end=2026-12-01').status_code == 422
        assert client.post('/api/macro/explain', json={'snapshot_id': '../.env'}).status_code == 422
        assert client.post('/api/macro/explain', json={'snapshot_id': 'f'*24}).status_code == 409


def raw_answer(text='公布值为{{E_ACTUAL}}。', ids=None):
    claim = {'kind': 'fact', 'text': text, 'citations': ids or ['E_ACTUAL']}
    return {'conclusion': claim, 'insights': [claim], 'watch_next': '观察短端收益率。', 'limitations': '没有一致预期。', 'followups': ['如何理解传导？']}


def test_ai_bound_numbers_missing_and_fake_consensus():
    ctx = macro_ai.context_for(sample(actual=macro.metric('0.3%', '%')))
    assert '0.3%' in macro_ai.validate(raw_answer(), ctx)['conclusion']['text']
    for raw in [raw_answer('公布值为0.9%。'), raw_answer('公布值为{{E_FORECAST}}。', ['E_FORECAST']), raw_answer('本次超预期。'), raw_answer('没有数据。', ['FAKE'])]:
        with pytest.raises(ValueError): macro_ai.validate(raw, ctx)


def test_ai_institution_dispersion_excludes_models_stale_and_wrong_period():
    from server import public_forecasts as pf
    rows = []
    for ident, value, kind, period, stale in [('a', '.2', 'institution', '2026-09', False), ('b', '.4', 'institution', '2026-09', False), ('c', '9', 'model', '2026-09', False), ('d', '8', 'institution', '2026-09', True), ('e', '7', 'institution', '2026-08', False)]:
        r = pf.record('cpi_mom', period, str(float(value)), kind, ident, 'https://www.bls.gov/cpi/', '2026-10-01', '2026-10-15T00:00:00Z', source_id=ident)
        r.update(stale=stale, collectedAfterRelease=True)
        rows.append(r)
    ctx = macro_ai.context_for(sample(title='CPI 环比（季调）', actual=macro.metric('0.5', '%'), publicForecasts=rows))
    reg = ctx['registry']
    assert reg['E_BANK_COUNT']['value'] == 2
    assert reg['E_BANK_SPREAD']['value'] == .2
    assert reg['E_BANK_DELTA_0']['display'] == '+0.3百分点'
    assert reg['E_BANK_DELTA_1']['display'] == '+0.1百分点'
    assert 'E_BANK_DELTA_2' not in reg
    assert len(reg['E_BANK_MIN']['sources']) == 2
    assert reg['E_BANK_DELTA_0']['collectedAfterRelease'] is True
    for r in rows:
        r['indicator'] = 'pce_mom'
    pce = macro_ai.context_for(sample(title='PCE 环比', reference='September 2026', publicForecasts=rows))
    assert pce['registry']['E_BANK_COUNT']['value'] == 2


def test_unreleased_market_effect_is_hypothesis():
    ctx = macro_ai.context_for(sample())
    result = macro_ai.validate(raw_answer('若通胀偏高，美股可能承压。', ['E_EVENT']), ctx)
    assert result['conclusion']['kind'] == 'hypothesis'


def test_ai_followup_and_snapshot_binding(monkeypatch):
    first = macro.finalize(sample(actual=macro.metric('0.3%', '%')))
    second = macro.finalize(sample(actual=macro.metric('0.4%', '%')))
    histories = []
    async def fake(context, history, question, **kwargs):
        histories.append(history[:])
        return {'answer': macro_ai.validate(raw_answer(), context), 'model': 'test', 'usage': {}}
    monkeypatch.setattr(narrative, 'call_openai', fake)
    result = asyncio.run(macro_ai.explain(macro_ai.Request(snapshot_id=first['snapshotId'])))
    followup = asyncio.run(macro_ai.explain(macro_ai.Request(snapshot_id=first['snapshotId'], conversation_id=result['conversationId'], question='影响如何？')))
    assert followup['turn'] == 2 and len(histories[1]) == 1
    with pytest.raises(narrative.AIError):
        asyncio.run(macro_ai.explain(macro_ai.Request(snapshot_id=second['snapshotId'], conversation_id=result['conversationId'])))


def test_optional_provider_failure_keeps_official(monkeypatch):
    async def fake_public(start, end):
        return [sample(actual=macro.metric('0.3%', '%'))], [], [], []
    async def denied(*args, **kwargs):
        raise macro.MacroError(503, 'unavailable')
    monkeypatch.setattr(macro, 'public_events', fake_public)
    monkeypatch.setattr(macro, 'key', lambda: 'test-only')
    monkeypatch.setattr(macro, 'cached', denied)
    data = asyncio.run(macro.calendar(date(2026, 10, 1), date(2026, 11, 1)))
    assert data['consensusStatus'] == 'unavailable'
    assert data['events'][0]['actual']['value'] == .3
