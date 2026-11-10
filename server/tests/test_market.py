import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest

from server import market as m
from server.financials import fact
from server.valuation import Assumptions


def quote_payload(**overrides):
    return {'data': {'symbol':'AAPL','currency':'USD','close':'100','is_market_open':True,
        'timestamp': 1, 'last_quote_at':int(datetime(2026,11,6,20,59,tzinfo=timezone.utc).timestamp()), **overrides},
        'retrievedAt':'2026-11-06T21:00:00+00:00'}


def test_quote_uses_last_quote_time_not_candle_open():
    now=datetime(2026,11,6,21,tzinfo=timezone.utc)
    q=m.normalize_quote(quote_payload(), 'AAPL', now)
    assert q['usable'] and q['asOf']=='2026-11-06T20:59:00+00:00'
    assert not m.normalize_quote(quote_payload(last_quote_at=None), 'AAPL', now)['usable']
    assert not m.normalize_quote(quote_payload(), 'AAPL', now+timedelta(hours=1))['usable']
    assert m.normalize_quote(quote_payload(is_market_open=False), 'AAPL', now+timedelta(days=3))['usable']
    assert not m.normalize_quote(quote_payload(is_market_open=False), 'AAPL', now+timedelta(days=8))['usable']


@pytest.mark.parametrize('overrides',[{'symbol':'NVDA'},{'currency':'EUR'},{'close':'NaN'},{'close':'0'},{'last_quote_at':9999999999}])
def test_invalid_quotes_are_rejected(overrides):
    with pytest.raises(ValueError): m.normalize_quote(quote_payload(**overrides),'AAPL',datetime(2026,11,6,21,tzinfo=timezone.utc))


def test_history_rejects_duplicates_and_excludes_current_day():
    p={'data':{'meta':{'symbol':'AAPL','currency':'USD','interval':'1day'},'values':[
        {'datetime':'2026-11-06','close':'100'},{'datetime':'2026-11-09','close':'999'}]}}
    assert m.normalize_history(p,'AAPL',date(2026,11,9))=={date(2026,11,6):100}
    p['data']['values'].append({'datetime':'2026-11-06','close':'101'})
    with pytest.raises(ValueError):m.normalize_history(p,'AAPL',date(2026,11,9))


def histories():
    start=date(2026,7,1)
    days=[start+timedelta(days=i) for i in range(130) if (start+timedelta(days=i)).weekday()<5]
    a,b={},{}
    av=bv=100
    for i,day in enumerate(days):
        if i:
            r=((i%7)-3)*.002
            av*=1+.001+2*r;bv*=1+r
        a[day]=av;b[day]=bv
    return a,b


def test_beta_known_slope_and_missing_dates_do_not_bridge():
    a,b=histories(); today=max(b)+timedelta(days=1)
    result=m.paired_beta(a,b,today)
    assert result['beta']==pytest.approx(2)
    assert result['rSquared']==pytest.approx(1)
    del a[list(a)[10]]
    result=m.paired_beta(a,b,today)
    assert result['beta']==pytest.approx(2)
    assert result['windowTruncated']
    assert result['start']==list(b)[11].isoformat()
    del a[list(a)[-10]]
    with pytest.raises(ValueError): m.paired_beta(a,b,today)


def test_beta_rejects_old_or_insufficient_history():
    a,b=histories()
    with pytest.raises(ValueError):m.paired_beta(a,b,max(b)+timedelta(days=12))
    with pytest.raises(ValueError):m.paired_beta(dict(list(a.items())[-60:]),b,max(b)+timedelta(days=1))


def quarter():
    return {'end':'2026-09-30','stock':{'shares':fact(10,[{'end':'2026-09-30','value':10}]),'equity':fact(50)},
            'ttm':{'revenue':fact(100),'net_income':fact(20)}}


def test_split_correction_and_no_mutation_of_financial_evidence():
    q=quarter(); original=deepcopy(q); day=date(2026,9,30)
    values=m.market_multiples(q,{'price':20,'usable':True,'asOf':'2026-11-06'},{day:10},{day:100})
    assert values['shares']==100
    assert values['splitFactor']==10
    assert [values['metrics'][k]['value'] for k in ('pe','pb','ps')]==[100,40,20]
    assert q==original


def test_missing_split_basis_or_stale_quote_disables_multiples():
    q=quarter(); day=date(2026,9,30)
    for quote,raw in [(None,{day:100}),({'price':20,'usable':False}, {day:100}),({'price':20,'usable':True}, {})]:
        result=m.market_multiples(q,quote,{day:10},raw)
        assert all(v['value'] is None for v in result['metrics'].values())
    q['ttm']['net_income']=fact(-1)
    assert m.market_multiples(q,{'price':20,'usable':True},{day:10},{day:100})['metrics']['pe']['value'] is None


def test_price_is_rebuilt_from_snapshot_and_binding_rejects_other_period(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'SNAPSHOTS',tmp_path)
    r={'symbol':'AAPL','snapshotId':'a'*24}; q=quarter()
    s={'symbol':'AAPL','financialSnapshotId':'a'*24,'reportEnd':q['end'],'quote':{'price':20,'usable':True}}
    (tmp_path/('b'*24+'.json')).write_text(json.dumps(s))
    loaded=m.load_snapshot('b'*24,r,q)
    assert m.bind_assumptions(Assumptions(debt=0,shares=10,comparison_price=999),loaded).comparison_price==20
    with pytest.raises(m.MarketError):m.load_snapshot('b'*24,{**r,'symbol':'NVDA'},q)
    with pytest.raises(m.MarketError):m.load_snapshot('b'*24,r,{**q,'end':'2025-01-01'})


def test_adapter_auth_cache_and_secret_redaction(monkeypatch):
    m._cache.clear();monkeypatch.setattr(m,'_lock',asyncio.Lock());monkeypatch.setattr(m,'_last_call',0)
    monkeypatch.setattr(m,'api_key',lambda:'private-test-key')
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers['Authorization']=='apikey private-test-key'
        assert 'private-test-key' not in str(request.url)
        return httpx.Response(200,json=quote_payload()['data'])
    client=httpx.AsyncClient
    monkeypatch.setattr(m.httpx,'AsyncClient',lambda **kw:client(transport=httpx.MockTransport(handler),**kw))
    async def run():
        first=await m.fetch('quote','AAPL');second=await m.fetch('quote','AAPL')
        assert first==second
        assert 'private-test-key' not in json.dumps(first)
    asyncio.run(run())
    assert len(calls)==1


@pytest.mark.parametrize('code',[401,403,429,500])
def test_provider_failure_is_sanitized(monkeypatch,code):
    m._cache.clear();monkeypatch.setattr(m,'_lock',asyncio.Lock());monkeypatch.setattr(m,'_last_call',0)
    monkeypatch.setattr(m,'api_key',lambda:'private-test-key')
    client=httpx.AsyncClient
    monkeypatch.setattr(m.httpx,'AsyncClient',lambda **kw:client(transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json={'status':'error','code':code,'message':'private-test-key'})),**kw))
    with pytest.raises(m.MarketError) as e:asyncio.run(m.fetch('quote','AAPL'))
    assert 'private-test-key' not in str(e.value)


def test_missing_key_never_calls_provider(monkeypatch):
    monkeypatch.setattr(m,'api_key',lambda:'')
    with pytest.raises(m.MarketError) as e:asyncio.run(m.fetch('quote','AAPL'))
    assert e.value.status==503
