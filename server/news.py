import uuid
from .object_store import storage_path
"""Bounded public RSS ingestion. Rankings retain their actual scope and provenance."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from dotenv import dotenv_values
import httpx

from .sec import ROOT

CACHE = storage_path('server/cache/news')
SNAPSHOTS = storage_path('server/news_snapshots')
EDITIONS = storage_path('server/news_editions')
for folder in (CACHE, SNAPSHOTS, EDITIONS): folder.mkdir(parents=True, exist_ok=True)
UTC = timezone.utc
SYDNEY = ZoneInfo('Australia/Sydney')
TTL = 1800
LOCK = asyncio.Lock()
SEM = asyncio.Semaphore(4)
REDDIT_LOCK = asyncio.Lock()
REDDIT_LAST = 0.0
FAILED = {}
UA = 'ClaroraResearch/0.3 (public RSS research reader)'
ATOM = '{http://www.w3.org/2005/Atom}'
COMMUNITIES = ['stocks', 'investing', 'wallstreetbets', 'CryptoCurrency', 'Bitcoin']
FEEDS = [
    {'id': 'cnbc', 'name': 'CNBC', 'url': 'https://www.cnbc.com/id/100003114/device/rss/rss.html', 'category': 'stocks', 'kind': 'media'},
    {'id': 'coindesk', 'name': 'CoinDesk', 'url': 'https://www.coindesk.com/arc/outboundfeeds/rss', 'category': 'crypto', 'kind': 'media'},
    {'id': 'cointelegraph', 'name': 'Cointelegraph', 'url': 'https://cointelegraph.com/rss', 'category': 'crypto', 'kind': 'media'},
    {'id': 'fed', 'name': 'Federal Reserve', 'url': 'https://www.federalreserve.gov/feeds/press_all.xml', 'category': 'macro', 'kind': 'official'},
    {'id': 'sec', 'name': 'SEC', 'url': 'https://www.sec.gov/news/pressreleases.rss', 'category': 'stocks', 'kind': 'official'},
] + [{'id': 'reddit-' + c.lower(), 'name': 'r/' + c, 'url': f'https://www.reddit.com/r/{c}/top/.rss?t=day&limit=25',
       'category': 'crypto' if c in ('CryptoCurrency', 'Bitcoin') else 'stocks', 'kind': 'community'} for c in COMMUNITIES]
CRYPTO = re.compile(r'\b(bitcoin|crypto|ethereum|stablecoin|blockchain|token|BTC|ETH|solana)\b', re.I)
MACRO = re.compile(r'\b(federal reserve|fomc|inflation|CPI|PCE|payroll|interest rates?|treasury|tariffs?|economy|economic|recession|central bank|oil prices?|geopolitical)\b', re.I)
STOCKS = re.compile(r'\b(stocks?|shares?|earnings|nasdaq|s&p|wall street|nvidia|tesla|apple|microsoft|amazon|alphabet|meta|semiconductor|profits?|valuation)\b', re.I)


class NewsError(Exception):
    def __init__(self, status, message, retry_after=300):
        self.status, self.message = status, message
        self.retry_after = retry_after
        super().__init__(message)


def now(): return datetime.now(UTC)
def iso(d): return d.astimezone(UTC).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def date_time(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        try: d = parsedate_to_datetime(value)
        except (ValueError, TypeError): return None
    # A timezone-less feed is ambiguous: do not label it as UTC or as a new post.
    return d.astimezone(UTC) if d and d.tzinfo else None


def safe_url(value):
    try:
        p = urlparse(str(value).strip())
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443): return None
        host = p.hostname.lower()
        if host == 'localhost' or '.' not in host or host.endswith(('.local', '.internal')): return None
        try:
            if not ipaddress.ip_address(host).is_global: return None
        except ValueError: pass
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid', 'ref_src')]
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or '/', '', urlencode(sorted(query)), ''))
    except (ValueError, TypeError): return None


def plain(text, limit=700):
    soup = BeautifulSoup(str(text or ''), 'html.parser')
    for tag in soup(['script', 'style', 'iframe']): tag.decompose()
    return ' '.join(soup.get_text(' ', strip=True).split())[:limit]


def excerpt(text):
    value = plain(text, 2500)
    value = re.split(r'\s+submitted by\s+', value, flags=re.I)[0]
    words = value.split()
    # Feed preview only; no full article redistribution or claim of full-text reading.
    return (' '.join(words[:70]) + ('…' if len(words) > 70 else ''))[:650]


def categories(title, summary, default):
    text = title + ' ' + summary
    result = {default}
    for label, pattern in [('crypto', CRYPTO), ('macro', MACRO), ('stocks', STOCKS)]:
        if pattern.search(text): result.add(label)
    return sorted(result)


def parse_feed(text, source):
    root = ElementTree.fromstring(text)
    atom = root.tag == ATOM + 'feed'
    if not atom and root.tag != 'rss': raise ValueError('Unsupported feed format')
    entries = root.findall(ATOM + 'entry') if atom else root.findall('./channel/item')
    out, discarded = [], 0
    for rank, entry in enumerate(entries[:100], 1):
        if atom:
            title = entry.findtext(ATOM + 'title', '')
            link = next((e.attrib.get('href', '') for e in entry.findall(ATOM + 'link') if e.attrib.get('rel', 'alternate') == 'alternate'), '')
            # Reddit updated may be an edit timestamp; only published establishes 24h membership.
            published = entry.findtext(ATOM + 'published')
            if source['kind'] != 'community': published = published or entry.findtext(ATOM + 'updated')
            summary = entry.findtext(ATOM + 'summary') or entry.findtext(ATOM + 'content', '')
        else:
            title, link = entry.findtext('title', ''), entry.findtext('link', '')
            published = entry.findtext('pubDate') or entry.findtext('{http://purl.org/dc/elements/1.1/}date')
            summary = entry.findtext('description', '')
        title, summary, link, stamp = plain(title, 400), excerpt(summary), safe_url(link), date_time(published)
        if not title or not link or not stamp or stamp > now() + timedelta(minutes=5):
            discarded += 1; continue
        if source['kind'] == 'community' and urlparse(link).hostname not in ('www.reddit.com', 'reddit.com'):
            discarded += 1; continue
        if source['id'] == 'cnbc' and not any(p.search(title + ' ' + summary) for p in (CRYPTO, MACRO, STOCKS)):
            continue
        out.append({'id': digest(link), 'title': title, 'excerpt': summary, 'url': link, 'publishedAt': iso(stamp),
                    'sourceId': source['id'], 'source': source['name'], 'kind': source['kind'],
                    'categories': categories(title, summary, source['category']),
                    'rank': rank if source['kind'] == 'community' else None,
                    'metrics': None, 'evidenceScope': '社区帖文 RSS 预览，未核实观点' if source['kind'] == 'community' else 'RSS 标题与摘要，未读取全文'})
    return out, discarded


async def download(url, headers=None, params=None):
    async with SEM:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream('GET', url, headers={'User-Agent': UA, **(headers or {})}, params=params) as response:
                if response.status_code == 429:
                    retry = response.headers.get('Retry-After', '300')
                    seconds = int(retry) if retry.isdigit() else max(300, int((date_time(retry)-now()).total_seconds())) if date_time(retry) else 300
                    raise NewsError(429, '来源限流，稍后重试', max(300, min(seconds, 86400)))
                if response.status_code in (401, 402, 403): raise NewsError(503, '来源访问或额度不可用')
                response.raise_for_status()
                parts, size = [], 0
                async for part in response.aiter_bytes():
                    size += len(part)
                    if size > 3_000_000: raise NewsError(502, '来源响应超出大小限制')
                    parts.append(part)
                return b''.join(parts).decode('utf-8-sig')


async def source_download(source):
    global REDDIT_LAST
    if source['kind'] != 'community': return await download(source['url'])
    async with REDDIT_LOCK:
        delay = 2 - (time.monotonic()-REDDIT_LAST)
        if delay > 0: await asyncio.sleep(delay)
        try: return await download(source['url'])
        finally: REDDIT_LAST = time.monotonic()


def read_cache(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return None


def atomic_json(path, value):
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


async def get_source(source):
    path = CACHE / (source['id'] + '.json')
    cache = read_cache(path)
    failure = read_cache(CACHE / (source['id'] + '-failure.json'))
    if failure and date_time(failure.get('until')):
        FAILED[source['id']] = date_time(failure['until'])
    age = (now() - date_time(cache['retrievedAt'])).total_seconds() if cache else float('inf')
    error = None
    if 0 <= age < TTL:
        pass
    elif FAILED.get(source['id'], now()-timedelta(seconds=1)) > now():
        error = '来源暂不可用，正在冷却重试'
    else:
        try:
            raw = await source_download(source)
            rows, discarded = parse_feed(raw, source)
            cache = {'items': rows, 'retrievedAt': iso(now()), 'discarded': discarded}
            atomic_json(path, cache)
            FAILED.pop(source['id'], None)
            failure_path = CACHE / (source['id'] + '-failure.json')
            if failure_path.exists(): failure_path.unlink()
            age = 0
        except (httpx.HTTPError, NewsError, ValueError, UnicodeError, ElementTree.ParseError, DefusedXmlException) as exc:
            FAILED[source['id']] = now() + timedelta(seconds=exc.retry_after if isinstance(exc, NewsError) else 300)
            atomic_json(CACHE / (source['id'] + '-failure.json'), {'until': iso(FAILED[source['id']])})
            error = exc.message if isinstance(exc, NewsError) else '来源读取或解析失败'
    available = bool(cache and 0 <= age < 86400)
    rows = [{**item, 'retrievedAt': cache['retrievedAt'], 'stale': bool(error)} for item in cache['items']] if available else []
    status = {'id': source['id'], 'name': source['name'], 'url': source['url'], 'kind': source['kind'],
              'available': available, 'stale': bool(error and available), 'error': error,
              'retrievedAt': cache['retrievedAt'] if available else None, 'count': len(rows),
              'discarded': cache.get('discarded', 0) if available else 0}
    return rows, status


def x_key():
    return (dotenv_values(ROOT / '.env').get('X_BEARER_TOKEN', os.getenv('X_BEARER_TOKEN', '')) or '').strip()


X_QUERY = '($SPY OR $QQQ OR $NVDA OR $BTC OR $ETH OR Bitcoin OR FOMC OR "US inflation") lang:en -is:retweet'


def parse_x(payload):
    if not isinstance(payload, dict) or payload.get('errors'): raise ValueError('Invalid X response')
    out = []
    for post in payload.get('data', []):
        stamp, ident = date_time(post.get('created_at')), str(post.get('id', ''))
        if not re.fullmatch(r'\d{1,30}', ident) or not stamp: continue
        m = post.get('public_metrics', {})
        if not all(k in m for k in ('like_count', 'reply_count', 'quote_count')) or not ('retweet_count' in m or 'repost_count' in m):
            continue  # Missing interaction counts are not zeros.
        metrics = {k: int(m.get(k, 0)) for k in ('like_count', 'reply_count', 'retweet_count', 'quote_count')}
        metrics['retweet_count'] = int(m.get('repost_count', metrics['retweet_count']))
        if any(n < 0 for n in metrics.values()): continue
        text = plain(post.get('text'), 650)
        out.append({'id': digest('x-' + ident), 'title': text[:200], 'excerpt': text, 'url': f'https://x.com/i/web/status/{ident}',
                    'publishedAt': iso(stamp), 'sourceId': 'x', 'source': 'X', 'kind': 'community',
                    'categories': categories(text, '', 'stocks'), 'metrics': metrics, 'rank': None,
                    'sampleScore': metrics['like_count'] + 2*metrics['retweet_count'] + 2*metrics['quote_count'] + 3*metrics['reply_count'],
                    'evidenceScope': 'X 关键词样本，未核实社区观点'})
    out.sort(key=lambda e: (e['sampleScore'], e['publishedAt']), reverse=True)
    for i, item in enumerate(out, 1): item['rank'] = i
    return out


async def x_posts():
    status = {'id': 'x', 'name': 'X', 'url': 'https://docs.x.com/x-api/posts/search-recent-posts', 'kind': 'community',
              'available': False, 'stale': False, 'configured': bool(x_key()), 'count': 0}
    if not x_key(): return [], {**status, 'error': '未配置 X_BEARER_TOKEN；官方访问权限和额度需要单独开通'}
    cache_key = 'x-' + digest(x_key())
    cache = read_cache(CACHE / (cache_key + '.json'))
    age = (now()-date_time(cache['retrievedAt'])).total_seconds() if cache else float('inf')
    try:
        if not 0 <= age < 3600:
            if FAILED.get(cache_key, now()-timedelta(seconds=1)) > now(): raise NewsError(429, 'X 暂不可用，等待下一次重试')
            end = now() - timedelta(seconds=30)
            raw = await download('https://api.x.com/2/tweets/search/recent', headers={'Authorization': 'Bearer ' + x_key()},
                 params={'query': X_QUERY, 'start_time': iso(end-timedelta(hours=24)), 'end_time': iso(end),
                         'max_results': 100, 'tweet.fields': 'created_at,public_metrics', 'sort_order': 'recency'})
            payload = json.loads(raw)
            cache = {'items': parse_x(payload), 'retrievedAt': iso(now()), 'sampleCapped': bool(payload.get('meta', {}).get('next_token'))}
            atomic_json(CACHE / (cache_key + '.json'), cache)
        rows = [{**e, 'retrievedAt': cache['retrievedAt'], 'stale': False} for e in cache['items']]
        return rows, {**status, 'available': True, 'retrievedAt': cache['retrievedAt'], 'count': len(rows), 'sampleCapped': cache.get('sampleCapped', False)}
    except (httpx.HTTPError, NewsError, ValueError, TypeError, KeyError):
        FAILED[cache_key] = now() + timedelta(minutes=15)
        return [], {**status, 'error': 'X 接口暂不可用，请检查账户权限、额度和网络；不会用其他平台伪装 X 热榜'}


def within(item, hours):
    stamp = date_time(item.get('publishedAt'))
    return bool(stamp and now()-timedelta(hours=hours) <= stamp <= now()+timedelta(minutes=5))


def dedupe(items):
    # Only identical canonical URLs are deduplicated; similar headlines are not proof of the same event.
    unique = {}
    for item in sorted(items, key=lambda i: (i['stale'], -date_time(i['publishedAt']).timestamp())):
        unique.setdefault(item['url'], item)
    return sorted(unique.values(), key=lambda i: i['publishedAt'], reverse=True)


def prune():
    for folder, days, pattern in [(SNAPSHOTS, 2, r'[0-9a-f]{24}\.json'), (EDITIONS, 30, r'\d{4}-\d{2}-\d{2}\.json')]:
        for p in folder.glob('*.json'):
            if re.fullmatch(pattern, p.name) and (now().timestamp()-p.stat().st_mtime) > days*86400:
                p.unlink()


async def feed():
    async with LOCK:
        results = await asyncio.gather(*(get_source(s) for s in FEEDS))
        articles, reddit, statuses = [], [], []
        for source, (rows, status) in zip(FEEDS, results):
            statuses.append(status)
            if source['kind'] == 'community':
                reddit.append({'community': source['name'], 'items': [r for r in rows if within(r, 24)][:25], 'status': status,
                               'method': '社区 Top(day) RSS 顺序，再按发布时间限定最近 24 小时；不是全站排名，无点赞和评论数'})
            else: articles.extend(r for r in rows if within(r, 168))
        x, xs = await x_posts()
        statuses.append(xs)
        articles = dedupe(articles)[:150]
        x = [p for p in x if within(p, 24)]
        core = {'articles': articles, 'reddit': reddit, 'x': x, 'sources': statuses}
        ident = digest(core)
        snapshot = {'snapshotId': ident, 'capturedAt': iso(now()), 'windowStart': iso(now()-timedelta(hours=24)),
                    'editionDate': now().astimezone(SYDNEY).date().isoformat(), **core,
                    'xMethod': '固定金融关键词最近最多 100 条英文帖子；样本内按赞 + 2×转发 + 2×引用 + 3×回复排序，非 X 官方热榜',
                    'schedule': '后端运行时每 30 分钟刷新；X 最多每小时一次；按悉尼日期保存新闻目录，AI 只在点击时调用'}
        path = SNAPSHOTS / (ident + '.json')
        if not path.exists(): atomic_json(path, snapshot)
        else: snapshot = read_cache(path)
        # Daily editions store publisher news only, never a long-term social-content archive.
        if any(s['available'] and not s['stale'] and s['kind'] != 'community' for s in statuses):
            daily = {'date': now().astimezone(SYDNEY).date().isoformat(), 'updatedAt': iso(now()),
                     'articles': [e for e in articles if within(e, 24)], 'sources': [s for s in statuses if s['kind'] != 'community'],
                     'notice': '该日最后一次更新时的滚动 24 小时新闻目录，不是完整自然日新闻或自动 AI 简报'}
            atomic_json(EDITIONS / (daily['date'] + '.json'), daily)
        prune()
        return {**snapshot, 'checkedAt': iso(now()), 'backgroundEnabled': os.getenv('NEWS_BACKGROUND_ENABLED', '1') != '0'}


def load_snapshot(ident):
    if not re.fullmatch(r'[0-9a-f]{24}', ident): raise NewsError(422, '无效新闻快照')
    data = read_cache(SNAPSHOTS / (ident + '.json'))
    if not data or (now()-date_time(data['capturedAt'])).total_seconds() > 86400:
        raise NewsError(409, '新闻快照不存在或已超过一天，请刷新热点后重新分析')
    return data


def editions(day=None):
    if day:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day): raise NewsError(422, '日期格式无效')
        data = read_cache(EDITIONS / (day + '.json'))
        if not data: raise NewsError(404, '该日没有保存的新闻目录，服务离线期间不会补造归档')
        return data
    return {'dates': sorted([p.stem for p in EDITIONS.glob('*.json') if re.fullmatch(r'\d{4}-\d{2}-\d{2}', p.stem)], reverse=True)[:30]}


async def background():
    while True:
        try: await feed()
        except asyncio.CancelledError: raise
        except Exception:
            # Never log upstream request URLs, tokens or response bodies.
            logging.getLogger(__name__).warning('Scheduled market-news refresh failed; retrying next interval')
        await asyncio.sleep(TTL)
