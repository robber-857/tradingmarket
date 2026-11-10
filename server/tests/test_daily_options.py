import asyncio
from datetime import datetime, date, timedelta, timezone
import math
import pytest
from server import options as o, option_strategies as st, daily_brief as d, options_ai, news, narrative


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    for name in ('CACHE','SNAPSHOTS'):
        p=tmp_path/name;p.mkdir();monkeypatch.setattr(o,name,p)
    monkeypatch.setattr(d,'DB',tmp_path/'daily.sqlite3')
    monkeypatch.setattr(news,'now',lambda:datetime(2026,11,9,21,tzinfo=timezone.utc))
    monkeypatch.setattr(d,'settings',lambda:{'enabled':True,'hour':8,'timezone':'Australia/Sydney'})
    options_ai.SESSIONS.clear();options_ai.ACTIVE.clear();options_ai.CALLS.clear()


def test_bsm_known_benchmark_and_parity():
    c=o.bsm(100,100,1,.05,0,.2,'call');p=o.bsm(100,100,1,.05,0,.2,'put')
    assert c['price']==pytest.approx(10.45058357,abs=1e-7)
    assert p['price']==pytest.approx(5.573526,abs=1e-6)
    assert c['price']-p['price']==pytest.approx(100-100*math.exp(-.05))


@pytest.mark.parametrize('side',['call','put'])
def test_greeks_finite_differences_and_iv(side):
    s,k,t,r,q,v=103,100,.3,.04,.01,.27
    base=o.bsm(s,k,t,r,q,v,side);h=.001
    f=lambda S,T,R,Q,V:o.bsm(S,k,T,R,Q,V,side)['price']
    assert base['delta']==pytest.approx((f(s+h,t,r,q,v)-f(s-h,t,r,q,v))/(2*h),rel=1e-5)
    assert base['gamma']==pytest.approx((f(s+h,t,r,q,v)-2*base['price']+f(s-h,t,r,q,v))/h**2,rel=1e-4)
    assert base['vega']==pytest.approx((f(s,t,r,q,v+h)-f(s,t,r,q,v-h))/(2*h)/100,rel=1e-4)
    assert base['theta']==pytest.approx(-(f(s,t+h,r,q,v)-f(s,t-h,r,q,v))/(2*h)/365,rel=1e-4)
    assert base['rho']==pytest.approx((f(s,t,r+h,q,v)-f(s,t,r-h,q,v))/(2*h)/100,rel=1e-4)
    assert o.iv(s,k,t,r,q,base['price'],side)==pytest.approx(v,abs=1e-8)


def test_impossible_prices_and_american_put():
    assert o.iv(100,100,1,.04,0,120,'call') is None
    assert o.iv(100,100,0,.04,0,5,'call') is None
    assert o.american_crr(80,100,1,.05,0,.2,'put')>=max(20,o.bsm(80,100,1,.05,0,.2,'put')['price'])


def chain():
    rows=[]
    for k in (90,100,110):
        for side in ('call','put'):
            price=o.bsm(100,k,30/365,.04,0,.3,side)['price']
            rows.append({'id':f'{side}-{k}','expiry':'2026-12-09','strike':k,'side':side,'bid':price*.99,'ask':price*1.01,'mid':price,'last':price,'oi':100,'volume':500,'spreadPct':2})
    return {'symbol':'TEST','spot':100,'priceDate':'2026-11-09','sourceAsOf':'test fixture','chainAsOf':None,'retrievedAt':news.iso(news.now()),'contracts':rows,'reportedRows':3,'receivedRows':3,'sourceUrl':'https://www.nasdaq.com/market-activity/stocks/test/option-chain'}


def test_distribution_ratios_and_maxpain():
    r=o.analyze(chain(),o.AnalysisRequest(symbol='TEST'))
    assert r['totals']['callOi']==300 and r['totals']['oiRatio']==1
    assert r['maxPain']['strikes']==[100]
    assert r['maxPain']['payout']==200000
    assert len(r['unusual'])==6
    assert r['atm']['iv']==pytest.approx(.3,rel=.005)
    assert r['atm']['breakEvenHigh']-r['atm']['strike']==pytest.approx(r['atm']['straddle'])


def test_missing_oi_not_zero_and_wide_quotes():
    c=chain();c['contracts'][0]['oi']=None
    for r in c['contracts']:
        if r['strike']==100:r['spreadPct']=80
    r=o.analyze(c,o.AnalysisRequest(symbol='TEST'))
    assert r['totals']['missingOi']==1 and r['maxPain'] is None
    assert r['atm']['wideSpread'] and r['atm']['iv'] is None
    assert r['atm']['straddle']>0


def test_after_hours_earnings_not_covered_by_same_day_expiry():
    c=chain();ev={'date':'2026-12-09','time':'time-after-hours','symbol':'TEST'}
    r=o.analyze(c,o.AnalysisRequest(symbol='TEST'),ev)
    assert not r['eventCovered']
    ev['time']='time-pre-market'
    assert o.analyze(c,o.AnalysisRequest(symbol='TEST'),ev)['eventCovered']


def raw_chain():
    return {'retrievedAt':news.iso(news.now()),'data':{'lastTrade':'LAST TRADE: $100 (AS OF NOV 9, 2026)','totalRecord':2,'table':{'asOf':None,'rows':[
        {'expirygroup':'December 9, 2026'}, {'expirygroup':'','strike':'100','drillDownURL':'/market-activity/stocks/test/option-chain/call-put-options/test--261209c00100000','c_Bid':'4','c_Ask':'5','c_Volume':'--','c_Openinterest':'0','p_Bid':'5','p_Ask':'4'}]}}}


def test_parser_rejects_crossed_missing_adjusted_and_stale():
    p=raw_chain();r=o.parse_chain(p,'TEST')['contracts']
    assert r[0]['volume'] is None and r[0]['oi']==0 and r[1]['mid'] is None
    p['data']['table']['rows'][1]['drillDownURL']='/test1--261209c00100000'
    with pytest.raises(news.NewsError):o.parse_chain(p,'TEST')
    p=raw_chain();p['data']['lastTrade']='LAST TRADE: $100 (AS OF OCT 1, 2026)'
    with pytest.raises(news.NewsError):o.parse_chain(p,'TEST')


@pytest.mark.parametrize('v',['--','NaN','Infinity',-1,None])
def test_bad_market_numbers(v):assert o.number(v) is None


@pytest.mark.parametrize('legs,shares,profit,loss,roots',[
    ([('call',1,100,6)],0,None,600,[106]),
    ([('put',1,100,5)],0,9500,500,[95]),
    ([('call',-1,110,3)],100,1300,9700,[97]),
    ([('put',1,90,3)],100,None,1300,[103]),
    ([('call',1,100,6),('call',-1,110,3)],0,700,300,[103]),
    ([('put',1,100,5),('put',-1,90,2)],0,700,300,[97]),
    ([('put',-1,100,5),('put',1,90,2)],0,300,700,[97]),
    ([('call',-1,100,6),('call',1,110,3)],0,300,700,[103]),
    ([('call',1,100,6),('put',1,100,5)],0,None,1100,[89,111]),
    ([('put',1,80,1),('put',-1,90,3),('call',-1,110,3),('call',1,120,1)],0,400,600,[86,114]),
    ([('put',1,90,3),('call',-1,110,3)],100,1000,1000,[100]),
    ([('call',-1,100,6)],0,600,None,[106])])
def test_strategy_exact_bounds(legs,shares,profit,loss,roots):
    req=st.StrategyRequest(name='fixture',spot=100,stock_shares=shares,legs=[st.Leg(side=a,quantity=b,strike=c,premium=d) for a,b,c,d in legs])
    r=st.calculate(req)
    assert r['maxProfit']==profit and r['maxLoss']==loss and r['breakEvens']==roots


def briefing_snapshot():
    item={'id':'a'*24,'title':'Stocks react to inflation','excerpt':'Inflation at 3%.','url':'https://www.cnbc.com/test','source':'CNBC','sourceId':'cnbc','kind':'media','categories':['stocks','macro'],'publishedAt':news.iso(news.now()-timedelta(hours=1)),'retrievedAt':news.iso(news.now()),'stale':False,'evidenceScope':'RSS'}
    return {'snapshotId':'b'*24,'articles':[item],'reddit':[],'x':[],'windowStart':news.iso(news.now()-timedelta(days=1))}


def mock_answer():
    return {'answer':{'conclusion':{'kind':'inference','text':'关注通胀条件。','citations':['S_1']},'insights':[{'kind':'inference','text':'需要验证影响。','citations':['S_1']}],'watch_next':'继续核实来源。','limitations':'有限材料。','followups':['风险？']},'model':'test'}


def test_daily_idempotency_history_and_restart(monkeypatch):
    calls=[]
    async def feed():return briefing_snapshot()
    async def ai(*a,**kw):calls.append(1);return mock_answer()
    monkeypatch.setattr(news,'feed',feed);monkeypatch.setattr(narrative,'call_openai',ai)
    async def run():
        await asyncio.gather(d.generate(),d.generate())
        assert len(calls)==1
        assert d.listing('2026-11-10')['payload']['coverage']['crypto']==0
        assert (await d.generate(manual=True))['status']=='ready'
        assert len(calls)==1
        monkeypatch.setattr(news,'now',lambda:datetime(2026,11,10,21,tzinfo=timezone.utc))
        await d.generate();assert len(calls)==2
        assert len(d.listing()['editions'])==2
    asyncio.run(run())


def test_scheduler_cutoff_and_failure_backoff(monkeypatch):
    calls=[]
    async def feed():return briefing_snapshot()
    async def ai(*a,**kw):calls.append(1);raise narrative.AIError(503,'fixture unavailable')
    monkeypatch.setattr(news,'feed',feed);monkeypatch.setattr(narrative,'call_openai',ai)
    async def run():
        monkeypatch.setattr(news,'now',lambda:datetime(2026,11,9,20,59,tzinfo=timezone.utc))
        await d.tick();assert calls==[]
        monkeypatch.setattr(news,'now',lambda:datetime(2026,11,9,21,tzinfo=timezone.utc))
        with pytest.raises(narrative.AIError):await d.tick()
        assert d.listing()['editions'][0]['status']=='failed'
        await d.tick();assert len(calls)==1
        for hour in (22,23):
            monkeypatch.setattr(news,'now',lambda h=hour:datetime(2026,11,9,h,tzinfo=timezone.utc))
            with pytest.raises(narrative.AIError):await d.tick()
        monkeypatch.setattr(news,'now',lambda:datetime(2026,11,10,0,tzinfo=timezone.utc))
        await d.tick();assert len(calls)==3
    asyncio.run(run())


def test_interrupted_generation_requires_manual_retry(monkeypatch):
    with d.connect() as c:c.execute('INSERT INTO editions VALUES (?,?,?,?,?,?)',('2026-11-10','generating',1,news.iso(news.now()),None,None))
    async def feed():return briefing_snapshot()
    async def ai(*a,**kw):return mock_answer()
    monkeypatch.setattr(news,'feed',feed);monkeypatch.setattr(narrative,'call_openai',ai)
    async def run():
        with pytest.raises(news.NewsError):await d.generate()
        assert (await d.retry_interrupted())['status']=='ready'
    asyncio.run(run())


def test_option_ai_evidence_no_invented_numbers():
    r=o.analyze(chain(),o.AnalysisRequest(symbol='TEST'));ctx=options_ai.context(r)
    raw=mock_answer()['answer'];raw['conclusion']['text']='来源价格 {{N_1_1}}。';raw['conclusion']['citations']=['S_1','N_1_1']
    assert '100' in options_ai.validate(raw,ctx)['conclusion']['text']
    raw['conclusion']['text']='上涨概率 80%。'
    with pytest.raises(ValueError):options_ai.validate(raw,ctx)


def test_option_ai_snapshot_isolation(monkeypatch):
    r=o.analyze(chain(),o.AnalysisRequest(symbol='TEST'));news.atomic_json(o.SNAPSHOTS/(r['snapshotId']+'.json'),r)
    async def ai(*a,**kw):return mock_answer()
    monkeypatch.setattr(narrative,'call_openai',ai)
    async def run():
        first=await options_ai.explain(options_ai.Request(snapshot_id=r['snapshotId']))
        new=o.analyze(chain(),o.AnalysisRequest(symbol='TEST',rate=.06));news.atomic_json(o.SNAPSHOTS/(new['snapshotId']+'.json'),new)
        with pytest.raises(narrative.AIError):await options_ai.explain(options_ai.Request(snapshot_id=new['snapshotId'],conversation_id=first['conversationId']))
    asyncio.run(run())


def test_oi_peak_cannot_become_support_or_direction():
    ctx=options_ai.context(o.analyze(chain(),o.AnalysisRequest(symbol='TEST')))
    for text in ('持仓峰值就是支撑。','市场偏防守。','上方压力清晰。'):
        raw=mock_answer()['answer'];raw['conclusion']['text']=text
        with pytest.raises(ValueError):options_ai.validate(raw,ctx)
    raw=mock_answer()['answer'];raw['conclusion']['text']='持仓峰值不代表支撑。'
    assert options_ai.validate(raw,ctx)['conclusion']['text']==raw['conclusion']['text']


def test_atm_boolean_not_numeric_evidence():
    ctx=options_ai.context(o.analyze(chain(),o.AnalysisRequest(symbol='TEST')))
    assert not any(isinstance(v.get('value'),bool) for v in ctx['registry'].values())
    assert next(v for v in ctx['registry'].values() if v['label']=='利率假设(%)')['display']=='4%'
    assert next(v for v in ctx['registry'].values() if v['label'].startswith('ATM BSM IV'))['display'].endswith('%')


def test_numeric_citations_derived_only_from_verified_placeholders():
    ctx=options_ai.context(o.analyze(chain(),o.AnalysisRequest(symbol='TEST')))
    raw=mock_answer()['answer'];raw['conclusion']['text']='来源价格 {{N_1_1}}。'
    result=options_ai.validate(raw,ctx)
    assert result['conclusion']['citations']==['S_1','N_1_1']
    raw['conclusion']['text']='来源价格 {{N_1_999}}。'
    with pytest.raises(ValueError):options_ai.validate(raw,ctx)
    raw['conclusion']['text']='来源价格 {{N_1_1}}。';raw['conclusion']['citations']=['N_1_1']
    with pytest.raises(ValueError):options_ai.validate(raw,ctx)


@pytest.mark.parametrize('failure',['validation','timeout','unavailable'])
def test_option_ai_failure_returns_verified_explanation(monkeypatch, failure, caplog):
    r=o.analyze(chain(),o.AnalysisRequest(symbol='TEST'))
    news.atomic_json(o.SNAPSHOTS/(r['snapshotId']+'.json'),r)
    async def ai(*a,**kw):
        error=narrative.AIError(502 if failure=='validation' else 503,'unavailable')
        if failure=='validation':error.validation_reason='Unverified number or URL'
        raise error
    monkeypatch.setattr(narrative,'call_openai',ai)
    result=asyncio.run(options_ai.explain(options_ai.Request(snapshot_id=r['snapshotId'])))
    assert result['generationMode']=='evidence_summary'
    assert result['generationNotice']
    assert result['answer']['insights']
    assert result['responseId'] is None
    assert not options_ai.ACTIVE
    assert 'snapshot='+r['snapshotId'] in caplog.text
    for claim in [result['answer']['conclusion'],*result['answer']['insights']]:
        assert 'S_1' in claim['citations']
        assert all(i in result['citations'] for i in claim['citations'])
        assert '{{' not in claim['text']


def test_basic_explanation_handles_missing_atm_and_ratio():
    data=o.analyze(chain(),o.AnalysisRequest(symbol='TEST'))
    data['atm']=None
    data['totals']['oiRatio']=None
    result=options_ai.basic_answer(options_ai.context(data))
    assert any('缺少可用的平值组合' in c['text'] for c in result['insights'])
    assert not any('持仓比为' in c['text'] for c in result['insights'])
