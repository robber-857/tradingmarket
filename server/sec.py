"""SEC public-data adapter. No price feed, forecasts, or model-generated facts."""
import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
CACHE = ROOT / 'server' / 'cache'
CACHE.mkdir(exist_ok=True)
COMPANIES = {
    'INTC': {'cik': '0000050863', 'name': '英特尔', 'english': 'Intel Corporation'},
    'NVDA': {'cik': '0001045810', 'name': '英伟达', 'english': 'NVIDIA'},
    'AAPL': {'cik': '0000320193', 'name': '苹果', 'english': 'Apple'},
    'MSFT': {'cik': '0000789019', 'name': '微软', 'english': 'Microsoft'},
}
_lock = asyncio.Lock()
_directory_lock = asyncio.Lock()
_directory_memory = None
DIRECTORY_URL = 'https://www.sec.gov/files/company_tickers_exchange.json'
LISTED_EXCHANGES = {'Nasdaq', 'NYSE', 'CBOE', 'TXSE'}


class DataUnavailable(Exception):
    pass


class SymbolError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def normalize_symbol(symbol):
    if not isinstance(symbol,str): raise SymbolError(422,'股票代码必须是文本。')
    symbol = symbol.strip().upper().removeprefix('$')
    if not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,4})?', symbol):
        raise SymbolError(422, '请输入有效美股代码，例如 TSLA、AMD 或 BRK.B；不接受 URL 或路径。')
    return symbol.replace('.', '-')


def parse_directory(payload):
    if not isinstance(payload, dict) or not {'cik','name','ticker','exchange'}.issubset(payload.get('fields', [])):
        raise ValueError('Invalid SEC directory')
    records = {}
    for values in payload.get('data', []):
        if not isinstance(values,list) or len(values)!=len(payload['fields']): continue
        item = dict(zip(payload['fields'], values))
        try:
            ticker = normalize_symbol(item['ticker'])
            cik = int(item['cik'])
            if not 0 < cik < 10**10 or not isinstance(item['name'],str): continue
        except (ValueError, TypeError, KeyError, SymbolError): continue
        records[ticker] = {'symbol':ticker,'cik':str(cik).zfill(10),'name':COMPANIES.get(ticker,{}).get('name',item['name']),
                           'english':item['name'],'exchange':item.get('exchange'), 'marketSymbol':ticker.replace('-','.')}
    if not records: raise ValueError('Empty SEC directory')
    return records


async def company_directory():
    global _directory_memory
    async with _directory_lock:
        if _directory_memory and time.monotonic()-_directory_memory[0] < 60:
            return _directory_memory[1]
        path = CACHE / 'company-tickers-exchange.json'
        cached = read_cache(path)
        age = datetime.now(timezone.utc).timestamp()-path.stat().st_mtime if cached else float('inf')
        stale = False
        if age > 86400:
            identity = os.getenv('SEC_USER_AGENT','').strip()
            if '@' not in identity: raise DataUnavailable('请配置后端 SEC_USER_AGENT 联系邮箱。')
            try:
                async with _lock:
                    async with httpx.AsyncClient(headers={'User-Agent':identity,'Accept':'application/json'},timeout=30) as client:
                        response = await client.get(DIRECTORY_URL)
                        response.raise_for_status()
                        payload = response.json()
                        parse_directory(payload)
                        tmp = path.with_suffix('.tmp')
                        tmp.write_text(json.dumps(payload),encoding='utf-8');tmp.replace(path)
                        cached = payload
                        await asyncio.sleep(.25)
            except (httpx.HTTPError,ValueError,OSError) as exc:
                if cached is None or age > 7*86400:
                    raise DataUnavailable('SEC 股票目录暂不可用，请稍后重试；未用固定代码表冒充搜索结果。') from exc
                stale = True
        try: records = parse_directory(cached)
        except ValueError as exc: raise DataUnavailable('SEC 股票目录格式异常，暂停代码解析。') from exc
        result = {'records':records, 'source':{'kind':'ticker_directory','url':DIRECTORY_URL,
            'retrievedAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),
            'stale':stale,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},'count':len(records)}
        _directory_memory = (time.monotonic(),result)
        return result


async def search_companies(query):
    directory = await company_directory()
    query = query.strip().upper().removeprefix('$')
    canonical = query.replace('.','-')
    records = directory['records']
    if not query:
        candidates = [records[s] for s in ['AAPL','MSFT','NVDA','INTC','TSLA','AMD','AMZN','META'] if s in records]
    else:
        candidates = [v for s,v in records.items() if canonical in s or query in v['english'].upper() or query in v['name'].upper()]
        candidates.sort(key=lambda v:(v['symbol']!=canonical, not v['symbol'].startswith(canonical),v['exchange'] not in LISTED_EXCHANGES,len(v['symbol']),v['symbol']))
    return {'results':candidates[:12],'matched':len(candidates),'directoryCount':directory['count'],
            'source':directory['source'],'notice':'目录命中不代表模型适用；选择后核验申报格式、财务口径和行情权限。'}


async def resolve_company(symbol):
    symbol = normalize_symbol(symbol)
    if symbol in {'BTC','ETH','USDT'}:
        raise SymbolError(404,'加密资产不适用公司财报与 FCFF 模型。')
    directory = await company_directory()
    company = directory['records'].get(symbol)
    if not company: raise SymbolError(404,f'SEC 当前目录未找到 {symbol}。请核对代码；名称搜索可查看候选。')
    if company['exchange'] not in LISTED_EXCHANGES:
        raise SymbolError(422,'该证券为 OTC 或未确认交易所，当前研究范围为美国主要交易所上市证券。')
    return {**company,'directorySource':directory['source']}


def read_cache(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


async def fetch_company(symbol: str, refresh=False, company=None):
    company = company or await resolve_company(symbol)
    symbol = normalize_symbol(company.get('symbol',symbol))
    identity = os.getenv('SEC_USER_AGENT', '').strip()
    if not identity or '@' not in identity or 'example.com' in identity:
        raise DataUnavailable('请在后端 .env 中配置 SEC_USER_AGENT（应用名称与联系邮箱）。')
    result, sources = {}, []
    # Serialize requests; comfortably below the SEC 10 requests/second limit.
    async with _lock:
        async with httpx.AsyncClient(headers={'User-Agent': identity, 'Accept': 'application/json'}, timeout=30) as client:
            for kind in ('facts', 'submissions'):
                path = CACHE / f'{symbol}-{kind}.json'
                cik = company['cik']
                url = (f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
                       if kind == 'facts' else f'https://data.sec.gov/submissions/CIK{cik}.json')
                cached = read_cache(path)
                if cached and str(cached.get('cik','')).lstrip('0') != str(cik).lstrip('0'):
                    cached = None  # A reused ticker must never inherit the former issuer's financials.
                age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime if cached else float('inf')
                stale = False
                # Force refresh is coalesced for a minute to avoid request flooding.
                should_fetch = not cached or age > (60 if refresh else 3600)
                if should_fetch:
                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            raise SymbolError(422, 'SEC 尚未提供该发行人的可用 XBRL 财报；基金、近期上市或特殊申报可能不适用。')
                        response.raise_for_status()
                        value = response.json()
                        if 'cik' not in value or int(value['cik']) != int(cik):
                            raise ValueError('Missing company identifier')
                        tmp = path.with_suffix('.tmp')
                        tmp.write_text(json.dumps(value), encoding='utf-8')
                        tmp.replace(path)
                        cached = value
                        await asyncio.sleep(.25)
                    except (httpx.HTTPError, ValueError, TypeError, OSError) as exc:
                        if cached is None:
                            raise DataUnavailable('SEC 暂不可用，请稍后重试；未用演示数字替代。') from exc
                        stale = True
                raw = path.read_bytes()
                result[kind] = cached
                sources.append({'kind': kind, 'url': url,
                                'retrievedAt': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                                'sha256': hashlib.sha256(raw).hexdigest(), 'stale': stale,
                                'status': 'stale_cache' if stale else 'cached' if not should_fetch else 'fetched'})
    return result['facts'], result['submissions'], sources
