import asyncio
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from server import options,news,options_ai,narrative,live_strategies as live
from server.app import app


@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(options,'SNAPSHOTS',tmp_path)
    monkeypatch.setattr(news,'now',lambda:datetime(2026,11,10,12,tzinfo=timezone.utc))
    options_ai.SESSIONS.clear();options_ai.ACTIVE.clear();options_ai.CALLS.clear()


def chain():
    rows=[]
    for k in (80,90,100,110,120):
        for side in ('call','put'):
            rows.append({'id':f'TEST-2026-12-18-{side}-{k}','side':side,'strike':k,'expiry':'2026-12-18',
                'bid':4 if k==100 else 1,'ask':6 if k==100 else 2,'mid':5 if k==100 else 1.5,
                'spreadPct':20,'oi':100,'volume':20,'iv':.3,
                'greeks':{'delta':.6 if side=='call' else -.4,'gamma':.02,'theta':-.1,'vega':.2,'rho':.05 if side=='call' else -.05}})
    c={'symbol':'TEST','snapshotId':'c'*24,'contracts':rows,'expiry':'2026-12-18','spot':100,'calculatedAt':news.iso(news.now()),
       'retrievedAt':news.iso(news.now()),'sourceAsOf':'fixture dated 2026-11-10','chainAsOf':None,'assumptions':{'rate':.04,'dividendYield':0},'sourceUrl':'https://www.nasdaq.com/market-activity/stocks/test/option-chain'}
    save(c);return c


def save(c):news.atomic_json(options.SNAPSHOTS/(c['snapshotId']+'.json'),c)


def req(c,legs=None,**kw):
    spec={'name':'test','legs':legs or [{'contract_id':'TEST-2026-12-18-call-100','quantity':1}]}
    return live.CompareRequest(chain_snapshot_id=c['snapshotId'],scenarios=[spec],**kw)


def test_natural_mid_fee_and_exact_payoff():
    c=chain();legs=[{'contract_id':'TEST-2026-12-18-call-100','quantity':1},{'contract_id':'TEST-2026-12-18-call-110','quantity':-1}]
    r=live.compare(req(c,legs,fee_per_contract=.65))['strategies'][0]
    assert [l['entryPrice'] for l in r['legs']]==[6,1]
    assert r['fees']==1.3 and r['netDebit']==pytest.approx(501.3)
    assert r['maxLoss']==pytest.approx(501.3) and r['maxProfit']==pytest.approx(498.7)
    assert r['breakEvens']==[105.013]
    mid=live.compare(req(c,legs,price_basis='mid',fee_per_contract=.65))['strategies'][0]
    assert mid['netDebit']==pytest.approx(351.3)
    assert r['greeks']==mid['greeks']  # risk model uses chain mids, not entry basis


def test_stock_delta_sign_quantity_and_greek_units():
    c=chain();request=req(c)
    request.scenarios[0].stock_shares=100;request.scenarios[0].legs[0].quantity=-2
    r=live.compare(request)['strategies'][0]
    assert r['greeks']=={'delta':-20,'gamma':-4,'theta':20,'vega':-40,'rho':-10}
    assert r['maxLoss'] is None  # 100 shares do not cover two short calls
    assert r['optionDebit']==-800 and r['netDebit']==9200


def test_missing_greeks_never_partial_sum():
    c=chain();c['contracts'][4]['greeks']=None;save(c)
    r=live.compare(req(c))['strategies'][0]
    assert all(v is None for v in r['greeks'].values())
    assert not r['greekCoverage']['complete'] and r['maxLoss']==600


@pytest.mark.parametrize('bid,ask',[(None,6),(4,None),(7,6),(0,0)])
def test_missing_and_crossed_quote_no_last_fallback(bid,ask):
    c=chain();c['contracts'][4].update(bid=bid,ask=ask,last=5);save(c)
    with pytest.raises(news.NewsError):live.compare(req(c))


def test_zero_bid_is_not_missing_but_warns():
    c=chain();c['contracts'][4].update(bid=0,ask=6,mid=None,greeks=None);save(c)
    r=req(c);r.scenarios[0].legs[0].quantity=-1
    result=live.compare(r)['strategies'][0]
    assert result['optionDebit']==0 and any('零买价' in n for n in result['riskNotes'])
    with pytest.raises(news.NewsError):live.compare(req(c,price_basis='mid'))


def test_reject_unknown_foreign_and_different_expiry():
    c=chain()
    for ident in ('OTHER-2026-12-18-call-100','TEST-2027-01-15-call-100','../.env'):
        with pytest.raises(news.NewsError):live.compare(req(c,[{'contract_id':ident,'quantity':1}]))


@pytest.mark.parametrize('age,source_age',[(901,0),(0,1801)])
def test_expired_evidence_rejected(age,source_age):
    c=chain();c['calculatedAt']=news.iso(news.now()-timedelta(seconds=age));c['retrievedAt']=news.iso(news.now()-timedelta(seconds=source_age));save(c)
    with pytest.raises(news.NewsError) as e:live.compare(req(c))
    assert e.value.status==409


def test_expired_contract_and_wrong_snapshot_mode():
    c=chain();c['expiry']='2026-11-09';save(c)
    with pytest.raises(news.NewsError):live.compare(req(c))
    c=chain();c['mode']='strategy';save(c)
    with pytest.raises(news.NewsError):live.compare(req(c))


def test_no_client_prices_or_duplicate_legs():
    c=chain();body=req(c).model_dump();body['scenarios'][0]['legs'][0]['premium']=.01
    with pytest.raises(ValidationError):live.CompareRequest(**body)
    body=req(c).model_dump();body['scenarios'][0]['legs']*=2
    with pytest.raises(ValidationError):live.CompareRequest(**body)
    for qty in (0,1.5,11,True):
        body=req(c).model_dump();body['scenarios'][0]['legs'][0]['quantity']=qty
        with pytest.raises(ValidationError):live.CompareRequest(**body)


def test_templates_are_real_contracts_with_correct_structure():
    c=chain();ts=live.templates(c['snapshotId'])['templates'];assert len(ts)==11
    for t in ts:
        assert t['available'] and all(l['contract_id'] in {r['id'] for r in c['contracts']} for l in t['legs'])
    condor=next(t for t in ts if t['id']=='iron-condor')
    assert [l['quantity'] for l in condor['legs']]==[1,-1,-1,1]
    c['contracts']=[r for r in c['contracts'] if r['strike']==100];save(c)
    assert not next(t for t in live.templates(c['snapshotId'])['templates'] if t['id']=='iron-condor')['available']


def test_snapshot_changes_with_basis_fees_and_contracts():
    c=chain();a=live.compare(req(c));b=live.compare(req(c,price_basis='mid'));d=live.compare(req(c,fee_per_contract=1))
    assert len({a['snapshotId'],b['snapshotId'],d['snapshotId']})==3
    assert options.load_snapshot(a['snapshotId'])['mode']=='live_strategy_comparison'


def test_ai_context_is_quote_backed_and_not_demo():
    data=live.compare(req(chain()));ctx=options_ai.context(data)
    assert ctx['mode']=='live_strategy_comparison' and 'Nasdaq' in ctx['registry']['S_1']['label']
    delta=next(v for v in ctx['registry'].values() if v['label'].endswith('delta'))
    assert delta['value']==60 and '股等效' in delta['display'] and '$' not in delta['display']
    assert ctx['evidence']['strategies'][0]['legs'][0]['entryPrice']==6


def test_comparison_api_bad_requests_and_session_isolation(monkeypatch):
    c=chain()
    with TestClient(app) as client:
        assert client.get('/api/options/live-templates',params={'snapshot_id':'../.env'}).status_code==422
        assert client.post('/api/options/compare',json=req(c).model_dump()).status_code==200
    claim={'kind':'hypothesis','text':'关注组合风险。','citations':['S_1']}
    async def fake(*a,**k):return {'answer':{'conclusion':claim,'insights':[claim],'watch_next':'核实报价。','limitations':'延迟数据。','followups':['风险？']},'model':'test'}
    monkeypatch.setattr(narrative,'call_openai',fake)
    async def run():
        a=live.compare(req(c));first=await options_ai.explain(options_ai.Request(snapshot_id=a['snapshotId']))
        b=live.compare(req(c,price_basis='mid'))
        with pytest.raises(narrative.AIError):await options_ai.explain(options_ai.Request(snapshot_id=b['snapshotId'],conversation_id=first['conversationId']))
    asyncio.run(run())
