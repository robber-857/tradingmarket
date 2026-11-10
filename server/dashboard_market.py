"""Bounded public market overview. Quotes are indicative, never synthetic."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import math
import time
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from . import news

CATALOG = [
    ('nasdaq100', '^NDX', 'Nasdaq 100', '指数', '点'),
    ('gold', 'GC=F', '黄金', 'COMEX 黄金期货', 'USD/盎司'),
    ('bitcoin', 'BTC-USD', 'BTC', '比特币 / 美元', 'USD'),
    ('sp500', '^GSPC', '标普 500', '指数', '点'),
    ('silver', 'SI=F', '白银', 'COMEX 白银期货', 'USD/盎司'),
    ('treasury10y', '^TNX', '美国 10 年期国债', '到期收益率', '%'),
    ('dollar', 'DX-Y.NYB', '美元指数', '美元指数现货', '点'),
    ('vix', '^VIX', 'VIX', '标普隐含波动率指数', '点'),
]
CACHE = news.ROOT / 'server/cache/dashboard_market'
_cache = {}
_lock = asyncio.Lock()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def parse_chart(body, symbol):
    result = body['chart']['result'][0]
    meta = result['meta']
    price, timestamp = meta.get('regularMarketPrice'), meta.get('regularMarketTime')
    if meta.get('symbol') != symbol or not finite(price) or not finite(timestamp):
        raise ValueError('Missing or mismatched quote')
    if timestamp > time.time() + 300:
        raise ValueError('Future quote')
    zone = ZoneInfo(meta.get('exchangeTimezoneName') or 'America/New_York')
    quote_day = datetime.fromtimestamp(timestamp, zone).date()
    closes = result['indicators']['quote'][0]['close']
    pairs = [(t, c) for t, c in zip(result.get('timestamp', []), closes)
             if finite(t) and finite(c)]
    previous = [(t, c) for t, c in pairs if datetime.fromtimestamp(t, zone).date() < quote_day]
    # chartPreviousClose is the start-of-range baseline, not yesterday's close.
    baseline = max(previous)[1] if previous else None
    change = price - baseline if baseline is not None else None
    return {'price':price,'previousClose':baseline,'change':change,
            'changePct':change / baseline * 100 if baseline else None,
            'asOf':datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            'history':[{'time':t,'value':c} for t,c in sorted(pairs) if t <= timestamp],
            'quoteOld':time.time() - timestamp > 96 * 3600}


async def get_item(client, spec):
    ident, symbol, name, description, unit = spec
    base = {'id':ident,'symbol':symbol,'name':name,'description':description,'unit':unit,
            'source':'Yahoo Finance','sourceUrl':'https://finance.yahoo.com/quote/'+quote(symbol,safe='')+'/'}
    path = CACHE / (ident+'.json')
    try:
        response = await client.get('https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe=''),
                                    params={'interval':'1d','range':'1mo'})
        response.raise_for_status()
        parsed = parse_chart(response.json(), symbol)
        result = {**base,**parsed,'available':True,'stale':False,'retrievedAt':news.iso(news.now())}
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            news.atomic_json(path, result)
        except OSError:
            pass  # A disk-cache failure must not discard a valid live quote.
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, OSError):
        cached = news.read_cache(path)
        if cached and cached.get('symbol') == symbol:
            return {**cached,**base,'stale':True,'notice':'行情更新失败，展示上次取得的数据'}
        return {**base,'available':False,'stale':False,'price':None,'change':None,'changePct':None,
                'asOf':None,'history':[],'notice':'行情暂不可用'}


async def overview():
    async with _lock:
        if _cache and time.monotonic() - _cache['time'] < 300:
            return deepcopy(_cache['data'])
        async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),headers={'User-Agent':'Mozilla/5.0'}) as client:
            items = await asyncio.gather(*(get_item(client,spec) for spec in CATALOG))
        result = {'items':items,'retrievedAt':news.iso(news.now()),
                  'notice':'参考行情，可能延迟；涨跌相对前一交易日收盘。BTC 相对前一 UTC 日收盘；收益率变化以基点表示。'}
        _cache.update(time=time.monotonic(),data=result)
        return deepcopy(result)
