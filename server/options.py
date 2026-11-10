"""Public delayed chains, explicit model assumptions, deterministic option research."""
import asyncio
from datetime import date, datetime, time, timedelta
import math
import re
from zoneinfo import ZoneInfo
import httpx
from pydantic import BaseModel, ConfigDict, Field
from . import news
from .sec import normalize_symbol

ET = ZoneInfo('America/New_York')
CACHE = news.ROOT / 'server/cache/options'
SNAPSHOTS = news.ROOT / 'server/option_snapshots'
for folder in (CACHE, SNAPSHOTS): folder.mkdir(parents=True, exist_ok=True)
FETCH_LOCK = asyncio.Lock()
VERSION = 'options-math-1.0'
OIC = 'https://www.optionseducation.org/advancedconcepts/black-scholes-formula'


def number(v):
    try:
        n = float(str(v).replace(',', '').replace('$', ''))
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError): return None


def cdf(x): return .5 * (1 + math.erf(x / math.sqrt(2)))


def bsm(s, k, t, r, q, vol, side):
    if s <= 0 or k <= 0 or t <= 0 or vol <= 0 or side not in ('call', 'put'): raise ValueError('Invalid option inputs')
    root = math.sqrt(t)
    d1 = (math.log(s/k) + (r-q+vol*vol/2)*t)/(vol*root)
    d2 = d1-vol*root
    ds, dk = math.exp(-q*t), math.exp(-r*t)
    phi = math.exp(-d1*d1/2)/math.sqrt(2*math.pi)
    call = side == 'call'
    price = s*ds*cdf(d1)-k*dk*cdf(d2) if call else k*dk*cdf(-d2)-s*ds*cdf(-d1)
    theta = -s*ds*phi*vol/(2*root)
    theta += q*s*ds*cdf(d1)-r*k*dk*cdf(d2) if call else -q*s*ds*cdf(-d1)+r*k*dk*cdf(-d2)
    return {'price': price, 'delta': ds*(cdf(d1) if call else cdf(d1)-1),
            'gamma': ds*phi/(s*vol*root), 'theta': theta/365,
            'vega': s*ds*phi*root/100,
            'rho': (k*t*dk*cdf(d2) if call else -k*t*dk*cdf(-d2))/100}


def iv(s, k, t, r, q, price, side):
    if price is None or price <= 0 or t <= 0: return None
    lo, hi = .0001, 5.0
    if not bsm(s,k,t,r,q,lo,side)['price'] < price < bsm(s,k,t,r,q,hi,side)['price']: return None
    for _ in range(65):
        mid = (lo+hi)/2
        if bsm(s,k,t,r,q,mid,side)['price'] < price: lo = mid
        else: hi = mid
    return (lo+hi)/2


def american_crr(s, k, t, r, q, vol, side, steps=160):
    dt = t/steps; u = math.exp(vol*math.sqrt(dt)); d = 1/u
    p = (math.exp((r-q)*dt)-d)/(u-d)
    if not 0 <= p <= 1: return None
    sign = 1 if side == 'call' else -1
    values = [max(sign*(s*u**j*d**(steps-j)-k), 0) for j in range(steps+1)]
    disc = math.exp(-r*dt)
    for n in range(steps-1, -1, -1):
        values = [max(disc*(p*values[j+1]+(1-p)*values[j]), sign*(s*u**j*d**(n-j)-k), 0) for j in range(n+1)]
    return values[0]


async def fetch(key, path, params, ttl):
    target = CACHE / (key + '.json')
    async with FETCH_LOCK:
        cached = news.read_cache(target)
        age = (news.now()-news.date_time(cached['retrievedAt'])).total_seconds() if cached else float('inf')
        if age < ttl: return cached
        failure = news.read_cache(CACHE / (key+'-failure.json'))
        if failure and news.date_time(failure['retryAt']) > news.now():
            raise news.NewsError(503, 'Nasdaq 来源正在冷却重试，请稍后再试；未用样本替代')
        try:
            async with httpx.AsyncClient(timeout=25, headers={'User-Agent':'MeridianResearch/0.4 (local research)', 'Accept':'application/json'}) as client:
                async with client.stream('GET', 'https://api.nasdaq.com/api/'+path, params=params) as response:
                    response.raise_for_status()
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 8_000_000: raise ValueError('Response too large')
            import json
            payload = json.loads(chunks)
            if not isinstance(payload.get('data'), dict): raise ValueError('No data')
            # Validate before preserving an upstream response as a usable cache.
            if 'option-chain' in path and not isinstance(payload['data'].get('table', {}).get('rows'), list): raise ValueError('No chain')
            if 'calendar' in path and not isinstance(payload['data'].get('rows'), list): raise ValueError('No calendar')
            result = {'retrievedAt':news.iso(news.now()), 'data':payload['data']}
            news.atomic_json(target, result)
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            news.atomic_json(CACHE/(key+'-failure.json'), {'retryAt':news.iso(news.now()+timedelta(minutes=5))})
            # An expired chain is not relabeled as current option positioning.
            raise news.NewsError(503, 'Nasdaq 公开数据暂不可用或该股票没有期权链，请稍后重试')


def parse_chain(payload, symbol):
    data = payload['data']; rows = data['table']['rows']; result = []; seen = set()
    m = re.search(r'\$([\d,.]+)', str(data.get('lastTrade')))
    spot = number(m[1]) if m else None
    dm = re.search(r'AS OF ([A-Z]+ \d{1,2}, \d{4})', str(data.get('lastTrade')).upper())
    try: price_day = datetime.strptime(dm[1], '%b %d, %Y').date() if dm else None
    except ValueError: price_day = None
    if not spot or not price_day or not 0 <= (news.now().astimezone(ET).date()-price_day).days <= 4:
        raise news.NewsError(503, '期权链标的价格日期缺失或过旧，无法可靠计算当前分布')
    group = None
    for row in rows:
        if row.get('expirygroup'):
            try: group = datetime.strptime(row['expirygroup'], '%B %d, %Y').date().isoformat()
            except ValueError: group = None
            continue
        k = number(row.get('strike'))
        contract = re.search(r'([a-z.\-]+?)(\d{6})[cp](\d{8})$', str(row.get('drillDownURL','')).lower())
        if not contract or not k or not group: continue
        try: expiry = datetime.strptime(contract[2], '%y%m%d').date().isoformat()
        except ValueError: continue
        if expiry != group or abs(int(contract[3])/1000-k) > .0001: continue
        # Adjusted roots may have non-standard deliverables. Only the requested standard root is accepted.
        if contract[1].rstrip('-').replace('.', '-') != symbol.lower().replace('.', '-'): continue
        expiry_time = datetime.combine(date.fromisoformat(expiry), time(16), ET)
        if expiry_time <= news.now(): continue
        for side, prefix in [('call','c'),('put','p')]:
            ident = f'{symbol}-{expiry}-{side}-{k:g}'
            if ident in seen: continue
            seen.add(ident)
            bid, ask = number(row.get(prefix+'_Bid')), number(row.get(prefix+'_Ask'))
            mid = (bid+ask)/2 if bid is not None and ask is not None and 0 < bid <= ask else None
            result.append({'id':ident,'expiry':expiry,'side':side,'strike':k,'bid':bid,'ask':ask,'mid':mid,
                           'last':number(row.get(prefix+'_Last')),'volume':number(row.get(prefix+'_Volume')),
                           'oi':number(row.get(prefix+'_Openinterest')),
                           'spreadPct':(ask-bid)/mid*100 if mid else None})
    if not result: raise news.NewsError(422, '没有可解析的未到期标准合约，不生成期权结论')
    return {'symbol':symbol,'spot':spot,'priceDate':price_day.isoformat(),'sourceAsOf':data.get('lastTrade'),
            'chainAsOf':data['table'].get('asOf'), 'retrievedAt':payload['retrievedAt'], 'contracts':result,
            'reportedRows':data.get('totalRecord'), 'sourceRowsReturned':len(rows),
            'truncated':bool(number(data.get('totalRecord')) and number(data['totalRecord'])>len(rows)),
            'receivedRows':sum(bool(number(r.get('strike'))) for r in rows),
            'sourceUrl':f'https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/option-chain'}


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str = Field(min_length=1,max_length=12)
    expiry: date | None = None
    rate: float = Field(default=.04, ge=0, le=.25, allow_inf_nan=False)
    dividend_yield: float = Field(default=0, ge=0, le=.25, allow_inf_nan=False)
    earnings_date: date | None = None


async def earnings(day):
    today = news.now().astimezone(ET).date()
    if not today <= day <= today+timedelta(days=14): raise news.NewsError(422, '财报日历仅查询美东今天至未来十四天')
    payload = await fetch('earnings-'+day.isoformat(),'calendar/earnings', {'date':day.isoformat()}, 21600)
    rows = [{'symbol':r.get('symbol'),'name':r.get('name'),'time':r.get('time'), 'marketCap':number(r.get('marketCap')),
             'date':day.isoformat(), 'sourceUrl':'https://www.nasdaq.com/market-activity/earnings'} for r in payload['data']['rows']
            if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}',str(r.get('symbol','')))]
    rows.sort(key=lambda r:r['marketCap'] or 0, reverse=True)
    return {'date':day.isoformat(),'rows':rows,'retrievedAt':payload['retrievedAt'],
            'notice':'Nasdaq 预计财报日程，按市值排序作为关注入口，并非期权热度榜；日期可能调整，需核对公司公告。'}


def sum_field(rows, field):
    vals = [r[field] for r in rows if r[field] is not None]
    return sum(vals) if vals else None


def analyze(chain, request, event=None):
    expiries = sorted({r['expiry'] for r in chain['contracts']})
    event_end = None
    if event:
        # When timing is unknown use end of day, so same-day expiry cannot be assumed to span earnings.
        event_end = datetime.combine(date.fromisoformat(event['date']), time(9,30) if event['time']=='time-pre-market' else time(20) if event['time']=='time-after-hours' else time(23,59), ET)
    threshold = event_end or news.now()+timedelta(days=7)
    default = next((e for e in expiries if datetime.combine(date.fromisoformat(e),time(16),ET)>threshold), expiries[0])
    expiry = request.expiry.isoformat() if request.expiry else default
    if expiry not in expiries: raise news.NewsError(422, '所选到期日不在这次来源返回的期权链内')
    t = (datetime.combine(date.fromisoformat(expiry),time(16),ET)-news.now()).total_seconds()/(365*86400)
    if t <= 0: raise news.NewsError(422, '所选合约已到期')
    rows = [dict(r) for r in chain['contracts'] if r['expiry']==expiry]
    s, rate, q = chain['spot'], request.rate, request.dividend_yield
    for r in rows:
        valid = r['spreadPct'] is not None and r['spreadPct'] <= 30
        r['iv'] = iv(s,r['strike'],t,rate,q,r['mid'],r['side']) if valid else None
        r['greeks'] = bsm(s,r['strike'],t,rate,q,r['iv'],r['side']) if r['iv'] else None
        r['volumeOi'] = r['volume']/r['oi'] if r['volume'] is not None and r['oi'] else None
        r['activityFlag'] = bool(r['volumeOi'] is not None and r['volumeOi']>=3 and r['volume']>=100 and r['oi']>=20 and valid)
    calls, puts = [r for r in rows if r['side']=='call'], [r for r in rows if r['side']=='put']
    co, po, cv, pv = sum_field(calls,'oi'),sum_field(puts,'oi'),sum_field(calls,'volume'),sum_field(puts,'volume')
    strikes = sorted({r['strike'] for r in rows})
    distribution = [{'strike':k, **{f'{side}_{field}':sum_field([r for r in rows if r['strike']==k and r['side']==side],field)
                                   for side in ('call','put') for field in ('oi','volume')}} for k in strikes]
    # Missing OI means we cannot reliably find even the sample's minimum payout point.
    pain = None
    if all(r['oi'] is not None for r in rows):
        payouts = [(k, sum(r['oi']*100*max((k-r['strike']) if r['side']=='call' else (r['strike']-k),0) for r in rows)) for k in strikes]
        minimum = min(v for _,v in payouts)
        pain = {'strikes':[k for k,v in payouts if abs(v-minimum)<.01], 'payout':minimum}
    k_atm = min(strikes,key=lambda k:abs(k-s))
    pair = [r for r in rows if r['strike']==k_atm]
    atm = None
    if len(pair)==2 and all(r['mid'] is not None for r in pair):
        premium = sum(r['mid'] for r in pair)
        ivs = [r['iv'] for r in pair if r['iv'] is not None]
        sigma = sum(ivs)/2 if len(ivs)==2 else None
        atm = {'strike':k_atm, 'straddle':premium,'premiumPct':premium/s*100, 'breakEvenLow':k_atm-premium,
               'breakEvenHigh':k_atm+premium,'askCost':sum(r['ask'] for r in pair),'bidValue':sum(r['bid'] for r in pair),
               'wideSpread':any(r['spreadPct']>30 for r in pair),'iv':sigma,'sigmaMove':s*sigma*math.sqrt(t) if sigma else None,
               'crr':{r['side']:american_crr(s,k_atm,t,rate,q,r['iv'],r['side']) for r in pair if r['iv']}}
    peak = lambda side: max([r for r in rows if r['side']==side and r['oi'] is not None],key=lambda r:r['oi'],default=None)
    end = datetime.combine(date.fromisoformat(expiry),time(16),ET)
    result = {k:v for k,v in chain.items() if k!='contracts'}
    result.update({'expiry':expiry,'expiries':expiries,'contracts':rows,'distribution':distribution,'atm':atm,
                   'totals':{'callOi':co,'putOi':po,'callVolume':cv,'putVolume':pv,'oiRatio':po/co if po is not None and co else None,
                             'volumeRatio':pv/cv if pv is not None and cv else None, 'missingOi':sum(r['oi'] is None for r in rows)},
                   'peakCall':peak('call'),'peakPut':peak('put'),'maxPain':pain,
                   'unusual':sorted([r for r in rows if r['activityFlag']],key=lambda r:r['volumeOi'],reverse=True)[:12],
                   'event':event,'eventCovered':bool(event_end and news.now()<event_end<end),
                   'assumptions':{'rate':rate,'dividendYield':q,'years':t,'multiplier':100,'expiryTime':'16:00 America/New_York'},
                   'calculatedAt':news.iso(news.now()),'engineVersion':VERSION,
                   'notice':'公开延迟数据；来源未提供逐合约报价时间。仅统计返回的标准合约；OI 是存量且可能为上一交易日，不能识别主动买卖。BSM 为欧式近似，股息率与利率是可调整假设，CRR 仅作美式提前行权敏感性比较。'})
    result['snapshotId'] = news.digest(result)
    return result


async def research(request):
    symbol = normalize_symbol(request.symbol)
    if not re.fullmatch(r'[A-Z][A-Z.\-]{0,9}',symbol): raise news.NewsError(422,'请输入有效美股代码')
    today = news.now().astimezone(ET).date()
    payload = await fetch('chain-'+symbol, f'quote/{symbol}/option-chain',
                          {'assetclass':'stocks','limit':9999,'fromdate':today.isoformat(),'todate':(today+timedelta(days=365)).isoformat(),
                           'money':'all','type':'all','excode':'oprac','callput':'callput'}, 900)
    chain = parse_chain(payload,symbol)
    event = None
    if request.earnings_date:
        calendar = await earnings(request.earnings_date)
        event = next((r for r in calendar['rows'] if r['symbol'].replace('.','-')==symbol),None)
        if not event: raise news.NewsError(422,'该来源在所选日期没有此股票财报记录，不将手动日期当成已确认财报')
    result = analyze(chain,request,event)
    news.atomic_json(SNAPSHOTS/(result['snapshotId']+'.json'), result)
    return result


def load_snapshot(ident):
    if not re.fullmatch(r'[0-9a-f]{24}',ident): raise news.NewsError(422,'无效期权快照')
    result = news.read_cache(SNAPSHOTS/(ident+'.json'))
    if not result or (news.now()-news.date_time(result['calculatedAt'])).total_seconds()>3600:
        raise news.NewsError(409,'期权快照不存在或超过一小时，请刷新期权分析')
    return result
