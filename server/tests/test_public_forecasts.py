import asyncio
from datetime import datetime, timezone

import pytest

from server import macro, public_forecasts as p, macro_ai

STAMP = '2026-11-09T20:00:00+00:00'
URL = 'https://www.scotiabank.com/content/globalweekahead20261106.pdf'
TABLE = """Country Date Time Indicator Period BNS Consensus Latest
US 11-10 08:30 CPI (m/m) Oct 0.3 0.2 0.6
US 11-10 08:30 CPI ex. Food & Energy (m/m) Oct 0.4 0.3 0.3
US 11-10 08:30 CPI (index) Oct -- 337.4 336.9
CA 11-10 08:30 CPI (m/m) Oct 0.9 0.9 0.1
US 11-10 08:30 Nonfarm Employment Report (000s m/m) Oct 100 60.0 29.0
US 11-10 08:30 PCE Deflator (m/m) Oct 0.5 0.4 0.3
US 11-10 08:30 PCE ex. Food & Energy (m/m) Oct 0.3 -- 0.2
"""

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'STORE', tmp_path/'forecasts.json')
    monkeypatch.setattr(macro, 'SNAPSHOTS', tmp_path)
    monkeypatch.setattr(macro, 'now', lambda: datetime.fromisoformat(STAMP))
    monkeypatch.setattr(p, 'LOCK', asyncio.Lock())


def data(rows):
    return {'records': rows, 'sources': [{'id': name, 'status': 'ok', 'checkedAt': STAMP} for name in ['scotia','cleveland']]}


def event(title='CPI 环比（季调）', reference='2026-10', release='2026-11-10T13:30:00+00:00'):
    return macro.event('CPI', title, release, reference, 'BLS', 'https://www.bls.gov')


def test_explicit_columns_units_country_and_indicator():
    rows=p.parse_scotia(TABLE, URL, STAMP)
    assert len(rows)==9
    assert {r['indicator'] for r in rows}=={'cpi_mom','core_cpi_mom','nfp','pce_mom','core_pce_mom'}
    nfp=[r for r in rows if r['indicator']=='nfp' and r['kind']=='consensus'][0]
    assert nfp['metric']['value']==60000
    assert all(r['reference']=='2026-10' for r in rows)
    assert [r['metric']['value'] for r in rows[:2]]==[.3,.2]


def test_changed_schema_rejected():
    with pytest.raises(ValueError): p.parse_scotia(TABLE.replace('BNS Consensus Latest','Latest BNS Consensus'),URL,STAMP)


def test_year_boundary():
    text=TABLE.splitlines()[0]+'\nUS 01-08 08:30 Nonfarm Employment Report (000s m/m) Dec 80 70 50'
    rows=p.parse_scotia(text,URL.replace('20261106','20261231'),'2027-01-01T00:00:00Z')
    assert rows[0]['reference']=='2026-12' and rows[0]['releaseDate']=='2027-01-08'


def nowcast_html():
    def table(basis):
        return f'<table><caption>Inflation, {basis} percent change</caption><tr>'+''.join(f'<th>{x}</th>' for x in ['Month','CPI','Core CPI','PCE','Core PCE','Updated'])+'</tr><tr><td>October 2026</td><td>0.24</td><td>0.21</td><td>0.27</td><td></td><td>11/09</td></tr></table>'
    return table('month-over-month')+table('year-over-year')


def test_models_separate_and_blanks_not_zero():
    rows=p.parse_cleveland(nowcast_html(),STAMP)
    assert len(rows)==6 and all(r['kind']=='model' for r in rows)
    e=event();p.attach([e],data(rows))
    assert e['forecast'] is None and len(e['publicForecasts'])==1
    with pytest.raises(ValueError): p.parse_cleveland(nowcast_html().replace('Core CPI','UNKNOWN'),STAMP)


def test_exact_period_and_pce_title_reference():
    rows=p.parse_scotia(TABLE,URL,STAMP)
    e=event('PCE 环比','Personal Income and Outlays, October 2026')
    wrong=event(reference='2026-09')
    p.attach([e,wrong],data(rows))
    assert e['forecast']['value']==.4 and wrong['forecast'] is None


def test_no_post_release_or_same_day_date_only_predictions():
    rows=p.parse_scotia(TABLE,URL,STAMP)
    e=event(release='2026-11-06T13:30:00Z');p.attach([e],data(rows))
    assert not e['publicForecasts'] and e['forecast'] is None


def test_historical_collection_is_labelled_and_cited():
    rows=p.parse_scotia(TABLE,URL,STAMP)
    e=event(release='2026-11-08T13:30:00Z');p.attach([e],data(rows))
    assert e['forecastCollectedAfterRelease']
    ctx=macro_ai.context_for(e)
    assert ctx['registry']['E_FORECAST']['sourceUrl']==URL
    assert len([k for k in ctx['registry'] if k.startswith('E_PUBLIC_')])==2


def test_source_failure_and_expired_checks_do_not_fill_consensus():
    rows=p.parse_scotia(TABLE,URL,STAMP)
    d=data(rows);d['sources'][0]['status']='error'
    e=event();p.attach([e],d)
    assert e['forecast'] is None and all(r['stale'] for r in e['publicForecasts'])
    d=data(rows);d['sources'][0]['checkedAt']='2026-11-01T00:00:00Z'
    e=event();p.attach([e],d)
    assert e['forecast'] is None


def test_sydney_dst_schedule_and_before_cutoff():
    assert p.schedule_day(datetime(2026,11,9,20,59,tzinfo=timezone.utc))=='2026-11-09'
    assert p.schedule_day(datetime(2026,11,9,21,tzinfo=timezone.utc))=='2026-11-10'
    assert p.schedule_day(datetime(2026,6,9,22,tzinfo=timezone.utc))=='2026-06-10'


def test_daily_idempotency_restart_failure_retains_records(monkeypatch):
    calls=[]
    async def fetch(*args,**kwargs):
        calls.append(args[1]);raise ValueError('source unavailable')
    monkeypatch.setattr(p,'fetch',fetch)
    d=p.read();d['records']=p.parse_scotia(TABLE,URL,STAMP);p.write(d)
    async def run():
        await asyncio.gather(p.update(),p.update())
        return await p.update()
    result=asyncio.run(run())
    assert len(calls)==4 and len(result['records'])==9
    assert all(s['status']=='error' for s in result['sources'])
    assert p.read()['scheduleDay']==p.schedule_day(macro.now())
