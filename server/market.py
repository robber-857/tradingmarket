from .object_store import storage_path
"""Server-only Twelve Data adapter and immutable, evidence-bound market snapshots."""
import asyncio
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
import time
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
import httpx

from .sec import ROOT, normalize_symbol
from .valuation import Assumptions, BetaInputs, calculate_beta, relative_valuation

PROVIDER = 'Twelve Data'
SOURCE = 'https://twelvedata.com/docs/market-data/time-series'
QUOTE_SOURCE = 'https://twelvedata.com/docs/market-data/quote'
VERSION = 'market-ols-1.0.0'
SNAPSHOTS = storage_path('server/market_snapshots')
_cache = OrderedDict()
_lock = asyncio.Lock()
_last_call = 0.0


class MarketError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def api_key():
    return (dotenv_values(ROOT / '.env').get('TWELVE_DATA_API_KEY', os.getenv('TWELVE_DATA_API_KEY', '')) or '').strip()


def status():
    return {'configured': bool(api_key()), 'provider': PROVIDER, 'benchmark': 'SPY',
            'notice': '配置不代表数据权限已验证。默认实时源覆盖部分交易场所；日线用于历史研究。'}


async def fetch(endpoint, symbol, **params):
    """Coalesce requests, keep keys out of URLs/logs, and share SPY history across assets."""
    global _last_call
    key = api_key()
    if not key:
        raise MarketError(503, '请先在项目 .env 配置 TWELVE_DATA_API_KEY，保存后点击刷新行情。')
    cache_key = (hashlib.sha256(key.encode()).hexdigest(), endpoint, symbol, tuple(sorted(params.items())))
    ttl = 60 if endpoint == 'quote' else 21600
    async with _lock:
        now = time.monotonic()
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < (30 if isinstance(cached[1], MarketError) else ttl):
            if isinstance(cached[1], MarketError): raise cached[1]
            return deepcopy(cached[1])
        # Basic accounts commonly allow eight credits/minute. Requests cost one credit each.
        await asyncio.sleep(max(0, 8.1 - (now - _last_call)))
        _last_call = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=10)) as client:
                response = await client.get(f'https://api.twelvedata.com/{endpoint}',
                    params={'symbol': symbol, 'country': 'United States', **params},
                    headers={'Authorization': f'apikey {key}'})
            if response.status_code in (401, 403):
                raise MarketError(503, 'Twelve Data 密钥或数据权限不可用，请核对账户配置。')
            if response.status_code == 429:
                raise MarketError(429, '行情请求额度或速率受限，请稍后刷新。')
            if response.status_code >= 400:
                raise MarketError(502, '行情数据源暂不可用，未使用演示数据替代。')
            body = response.json()
            if not isinstance(body, dict): raise ValueError('Invalid object')
            if body.get('status') == 'error':
                code = body.get('code')
                raise MarketError(429 if code == 429 else 503,
                    '行情额度受限，请稍后刷新。' if code == 429 else '数据源未提供所需行情，请核对密钥、套餐权限及股票覆盖。')
            result = {'data': body, 'retrievedAt': datetime.now(timezone.utc).isoformat()}
        except MarketError as exc:
            _cache[cache_key] = (time.monotonic(), exc)
            raise
        except (httpx.HTTPError, ValueError) as exc:
            error = MarketError(502, '行情服务连接失败或返回格式异常，请稍后刷新。')
            _cache[cache_key] = (time.monotonic(), error)
            raise error from exc
        _cache[cache_key] = (time.monotonic(), result)
        while len(_cache) > 64: _cache.popitem(last=False)
        return deepcopy(result)


def number(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0: raise ValueError('Invalid positive price')
    return result


def normalize_quote(payload, symbol, now):
    d = payload['data']
    if d.get('symbol') != symbol or d.get('currency') != 'USD': raise ValueError('Wrong instrument/currency')
    # timestamp is the candle opening time, NOT necessarily the last trade time.
    stamp = d.get('last_quote_at')
    at = datetime.fromtimestamp(int(stamp), timezone.utc) if stamp else None
    if at and at > now + timedelta(minutes=5): raise ValueError('Future quote')
    stale = at is None or now - at > timedelta(days=5) or (d.get('is_market_open') is True and now - at > timedelta(minutes=20))
    return {'symbol': symbol, 'price': number(d['close']), 'currency': 'USD',
            'asOf': at.isoformat() if at else None, 'barDate': d.get('datetime'),
            'retrievedAt': payload['retrievedAt'], 'marketOpen': d.get('is_market_open'),
            'stale': stale, 'usable': not stale, 'provider': PROVIDER, 'sourceUrl': QUOTE_SOURCE,
            'coverage': '默认实时源覆盖部分交易场所，不是全市场合并报价；不含盘前盘后。'}


def normalize_history(payload, symbol, today):
    meta = payload['data'].get('meta', {})
    if meta.get('symbol') != symbol or meta.get('currency') != 'USD': raise ValueError('Wrong history instrument')
    if meta.get('interval') != '1day': raise ValueError('Wrong frequency')
    rows = {}
    for item in payload['data'].get('values', []):
        day = date.fromisoformat(item['datetime'])
        if day >= today: continue  # Exclude the unfinished/current exchange-date candle.
        if day in rows: raise ValueError('Duplicate history date')
        rows[day] = number(item['close'])
    if not rows: raise ValueError('No completed bars')
    return dict(sorted(rows.items()))


def paired_beta(asset, benchmark, today):
    # Use the benchmark's completed daily calendar. Never bridge missing asset bars.
    dates = [d for d in benchmark if d >= today - timedelta(days=730)]
    suffix = []
    for day in dates:
        if day not in asset: suffix = []
        else: suffix.append(day)
    if len(suffix) < 61: raise ValueError('完整配对日线不足 61 个，暂不估计 Beta。')
    if (today - suffix[-1]).days > 7: raise ValueError('历史数据末端超过七天，暂停 Beta 估计。')
    sample = BetaInputs(benchmark='SPY', frequency='daily', prices=[
        {'date': d, 'asset': asset[d], 'benchmark': benchmark[d]} for d in suffix])
    result = calculate_beta(sample)
    result['basis'] = '过去最多两年、连续可配对交易日的拆股复权日收盘价；简单价格收益率 OLS（不含分红再投资），SPY 为市场代理。'
    result['adjustment'] = 'splits'
    result['sourceUrl'] = SOURCE
    result['provider'] = PROVIDER
    result['windowTruncated'] = len(suffix) < len(dates)
    return result


def market_multiples(quarter, quote, adjusted, raw):
    item = quarter['stock'].get('shares', {})
    shares = item.get('value')
    evidence = item.get('evidence', [])
    share_date = max((e.get('end') or '' for e in evidence), default='')
    factor = None
    split_basis = None
    if shares and share_date and raw and adjusted and max(raw) == max(adjusted):
        target = date.fromisoformat(share_date)
        dates = [d for d in raw if d <= target and d in adjusted]
        if dates and (target - max(dates)).days <= 7:
            factor = raw[max(dates)] / adjusted[max(dates)]
            split_basis = {'date':max(dates).isoformat(),'rawClose':raw[max(dates)],'splitAdjustedClose':adjusted[max(dates)],
                           'historyEnd':max(adjusted).isoformat()}
    corrected = shares * factor if shares and factor else None
    price = quote['price'] if quote and quote['usable'] and corrected else None
    result = relative_valuation(quarter, Assumptions(debt=0, shares=corrected or 1, comparison_price=price))
    result.update({'shares': corrected, 'reportedShares': shares, 'sharesAsOf': share_date or None,
        'splitFactor': factor, 'splitBasis':split_basis, 'reportEnd': quarter['end'], 'quoteAsOf': quote.get('asOf') if quote else None,
        'basis': '行情价格 × 最新已披露股数（以原始/拆股复权历史价格比修正拆股）估算市值；未计披露后回购、增发。倍数分母来自最新可得正式财报，不是历史回测。'})
    for name, metric in result['metrics'].items():
        metric['formula'] = metric['formula'].replace('手动价格 × 估值股数', '行情价格 × 拆股修正已披露股数')
        metric['warning'] = result['basis']
        metric['evidence'] = metric['evidence'] + evidence
        if price is None:
            metric['reason'] = '缺少可用报价或无法核验股数拆股口径，暂停计算'
    return result


async def build_market(report):
    symbol = report['symbol']
    normalize_symbol(symbol)
    provider_symbol = report.get('company',{}).get('marketSymbol',symbol)
    if not api_key(): raise MarketError(503, '请先在项目 .env 配置 TWELVE_DATA_API_KEY，保存后点击刷新行情。')
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo('America/New_York')).date()
    quote, adjusted, raw, benchmark, beta = None, {}, {}, {}, None
    issues, sources = [], []
    jobs = [('quote', provider_symbol, {}), ('time_series', provider_symbol, {'interval': '1day', 'outputsize': 600, 'adjust': 'splits'}),
            ('time_series', 'SPY', {'interval': '1day', 'outputsize': 600, 'adjust': 'splits'}),
            ('time_series', provider_symbol, {'interval': '1day', 'outputsize': 600, 'adjust': 'none'})]
    for i, (endpoint, ticker, params) in enumerate(jobs):
        try:
            payload = await fetch(endpoint, ticker, **params)
            sources.append({'provider': PROVIDER, 'symbol': ticker, 'endpoint': endpoint, 'parameters': params,
                            'retrievedAt': payload['retrievedAt'], 'url': QUOTE_SOURCE if i == 0 else SOURCE})
            if i == 0: quote = normalize_quote(payload, provider_symbol, now)
            elif i == 1: adjusted = normalize_history(payload, provider_symbol, today)
            elif i == 2: benchmark = normalize_history(payload, 'SPY', today)
            else: raw = normalize_history(payload, provider_symbol, today)
        except (MarketError, ValueError, TypeError, KeyError, OverflowError) as exc:
            issues.append(f'{ticker} {endpoint}: {exc.message if isinstance(exc, MarketError) else "数据字段校验失败"}')
    if adjusted and benchmark:
        try: beta = paired_beta(adjusted, benchmark, today)
        except ValueError as exc: issues.append(str(exc))
    quarter = next(q for q in report['quarters'] if q['end'] == report['latestReportEnd'])
    multiples = market_multiples(quarter, quote, adjusted, raw)
    if report.get('capabilities',{}).get('automaticMultiples') is False:
        multiples['marketCap'] = multiples['shares'] = None
        for item in multiples['metrics'].values():
            item.update(value=None,numerator=None,reason=report['capabilities']['multiplesReason'])
    if quote and quote['stale']: issues.append('报价时间缺失或已超过可用时限，未用于估值。')
    result = {'symbol': symbol, 'financialSnapshotId': report['snapshotId'], 'reportEnd': quarter['end'],
              'quote': quote, 'beta': beta, 'multiples': multiples, 'sources': sources, 'issues': issues,
              'history': [{'date': d.isoformat(), 'close': v} for d, v in adjusted.items() if d >= today - timedelta(days=730)],
              'betaPricePairs': [{'date':d.isoformat(),'asset':adjusted[d],'benchmark':benchmark[d]} for d in benchmark
                                 if beta and beta['start'] <= d.isoformat() <= beta['end'] and d in adjusted],
              'historyBasis': '拆股复权日收盘价（不含分红再投资）；当日未完成日线已排除。',
              'createdAt': now.isoformat(), 'modelVersion': VERSION}
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:24]
    result['marketSnapshotId'] = digest
    SNAPSHOTS.mkdir(exist_ok=True)
    (SNAPSHOTS / f'{digest}.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def load_snapshot(snapshot_id, report, quarter):
    path = SNAPSHOTS / f'{snapshot_id}.json'
    if not path.exists(): raise MarketError(409, '行情快照不存在，请刷新行情。')
    result = json.loads(path.read_text(encoding='utf-8'))
    if result['symbol'] != report['symbol'] or result['financialSnapshotId'] != report['snapshotId'] or result['reportEnd'] != quarter['end']:
        raise MarketError(409, '行情只与当前最新财报绑定，请切回最新报告期并刷新行情。')
    return result


def bind_assumptions(p, snapshot):
    # Price is always reconstructed from the persisted server snapshot.
    quote = snapshot.get('quote')
    price = quote['price'] if quote and quote['usable'] else None
    return p.model_copy(update={'comparison_price': price})
