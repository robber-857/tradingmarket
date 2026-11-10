import uuid
from .object_store import storage_path
"""Free public forecast facts. Deterministic parsing; no paid API or LLM calls."""
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
import json
import logging
import re
from statistics import median
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from . import macro
from . import institution_forecasts

STORE = storage_path('server/cache/public-forecasts.json')
LOCK = asyncio.Lock()
SYDNEY = ZoneInfo('Australia/Sydney')
SCOTIA = 'https://www.scotiabank.com/ca/en/about/economics/economics-publications.global-week-ahead.html'
CLEVELAND = 'https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting'
SOURCES = [('cleveland', CLEVELAND, 'Cleveland Fed（模型）'),
           ('scotia', SCOTIA, 'Scotiabank 公开周报（调查与机构）'),
           ('rbc', institution_forecasts.RBC, 'RBC Economics（机构）'),
           ('usbank', institution_forecasts.USBANK, 'U.S. Bank（机构）')]
MONTHS = {name: n for n, name in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}
# Full labels are deliberate: do not confuse index levels, nominal spending or private payrolls.
SCOTIA_LABELS = {
    'CPI (m/m)': 'cpi_mom', 'CPI (y/y)': 'cpi_yoy',
    'CPI ex. Food & Energy (m/m)': 'core_cpi_mom', 'CPI ex. Food & Energy (y/y)': 'core_cpi_yoy',
    'Nonfarm Employment Report (000s m/m)': 'nfp',
    'PCE Deflator (m/m)': 'pce_mom', 'PCE Deflator (y/y)': 'pce_yoy',
    'PCE ex. Food & Energy (m/m)': 'core_pce_mom', 'PCE ex. Food & Energy (y/y)': 'core_pce_yoy',
}
EVENT_LABELS = {
    'CPI 环比（季调）': 'cpi_mom', 'CPI 同比（未季调）': 'cpi_yoy',
    '核心 CPI 环比（季调）': 'core_cpi_mom', '核心 CPI 同比（未季调）': 'core_cpi_yoy',
    '非农就业月增量（季调）': 'nfp',
    'PCE 环比': 'pce_mom', '核心 PCE 环比': 'core_pce_mom',
    'PCE 同比': 'pce_yoy', '核心 PCE 同比': 'core_pce_yoy',
}


def record(code, period, raw, kind, source, url, updated, retrieved, release_date=None, *, source_id=None):
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', raw):
        return None
    numeric = float(raw) * (1000 if code == 'nfp' else 1)
    if not (-100 <= numeric <= 100) and code != 'nfp':
        raise ValueError('Invalid percent')
    item = {'indicator': code, 'reference': period, 'kind': kind, 'source': source,
            'sourceUrl': url, 'sourceUpdatedAt': updated, 'retrievedAt': retrieved,
            'releaseDate': release_date, 'metric': macro.metric(str(numeric), '人' if code == 'nfp' else '%'),
            'sourceId': source_id or ('cleveland' if kind == 'model' else 'scotia')}
    item['id'] = macro.digest([code, period, kind, source, url, updated, numeric])
    return item


def parse_scotia(text, url, retrieved):
    match = re.search(r'globalweekahead(\d{8})\.pdf$', url)
    if not match or not re.search(r'Country\s+Date\s+Time\s+Indicator\s+Period\s+BNS\s+Consensus\s+Latest', text):
        raise ValueError('Forecast table schema changed')
    published = datetime.strptime(match[1], '%Y%m%d').date()
    if published > macro.timestamp(retrieved).date():
        raise ValueError('Future publication')
    results = []
    pattern = r'^US\s+(\d{2})-(\d{2})\s+\d{2}:\d{2}\s+(.+?)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+([+−-]?[\d.]+|--)\s+([+−-]?[\d.]+|--)\s+([+−-]?[\d.]+|--)\s*$'
    for line in text.splitlines():
        m = re.fullmatch(pattern, line.strip())
        if not m or m[3] not in SCOTIA_LABELS:
            continue
        code = SCOTIA_LABELS[m[3]]
        # The table describes next week's releases, including a December/January rollover.
        candidates = [datetime(year, int(m[1]), int(m[2])).date() for year in (published.year-1, published.year, published.year+1)]
        release = min(candidates, key=lambda d: abs((d-published).days))
        if not 0 <= (release-published).days <= 14:
            continue
        month = MONTHS[m[4]]
        year = release.year - (month > release.month)
        period = f'{year:04d}-{month:02d}'
        for raw, kind, source in [(m[5], 'institution', 'Scotiabank Economics'),
                                  (m[6], 'consensus', 'Scotiabank 周报转引市场调查（表注：Bloomberg）')]:
            row = record(code, period, raw.replace('−', '-'), kind, source, url,
                         published.isoformat(), retrieved, release.isoformat())
            if row:
                results.append(row)
    return results


def parse_cleveland(html, retrieved):
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    checked = macro.timestamp(retrieved).date()
    found = set()
    for table in soup.find_all('table'):
        text = table.get_text(' ', strip=True).lower()
        basis = 'mom' if 'month-over-month percent change' in text else 'yoy' if 'year-over-year percent change' in text else None
        if not basis:
            continue
        headers = [c.get_text(' ', strip=True) for c in table.select('tr th')]
        if headers != ['Month', 'CPI', 'Core CPI', 'PCE', 'Core PCE', 'Updated']:
            raise ValueError('Nowcast table schema changed')
        found.add(basis)
        for tr in table.find_all('tr'):
            cells = [c.get_text(' ', strip=True) for c in tr.find_all('td')]
            if len(cells) != 6:
                continue
            try:
                period = datetime.strptime(cells[0], '%B %Y').strftime('%Y-%m')
                updated = datetime.strptime(f'{checked.year}/{cells[5]}', '%Y/%m/%d').date()
                if updated > checked:
                    updated = updated.replace(year=updated.year-1)
            except ValueError:
                continue
            if (checked-updated).days > 14:
                continue
            for i, prefix in enumerate(['cpi', 'core_cpi', 'pce', 'core_pce'], 1):
                row = record(prefix+'_'+basis, period, cells[i], 'model', 'Cleveland Fed Inflation Nowcasting',
                             CLEVELAND, updated.isoformat(), retrieved)
                if row:
                    results.append(row)
    if found != {'mom', 'yoy'} or not results:
        raise ValueError('No current nowcast tables')
    return results


def read():
    try:
        data = json.loads(STORE.read_text(encoding='utf-8'))
        if data.get('version') == 1:
            return data
    except (OSError, ValueError):
        pass
    return {'version': 1, 'records': [], 'sources': [], 'lastAttemptAt': None, 'scheduleDay': None}


def write(data):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(STORE)


def schedule_day(at):
    local = at.astimezone(SYDNEY)
    return (local.date() - timedelta(days=local.hour < 8)).isoformat()


async def fetch(client, url, pdf=False):
    # Only links discovered on these public source pages; no arbitrary user URLs.
    if urlparse(url).hostname not in ('www.scotiabank.com', 'www.clevelandfed.org', 'www.rbc.com', 'www.usbank.com') or not url.startswith('https://'):
        raise ValueError('Unexpected source host')
    response = await client.get(url)
    response.raise_for_status()
    if len(response.content) > 15_000_000:
        raise ValueError('Source too large')
    if pdf:
        if not response.content.startswith(b'%PDF'):
            raise ValueError('Expected PDF')
        return '\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(response.content)).pages[:30])
    return response.text


async def scotia(client, retrieved, previous):
    html = await fetch(client, SCOTIA)
    soup = BeautifulSoup(html, 'html.parser')
    links = list(dict.fromkeys(urljoin(SCOTIA, a['href']) for a in soup.select('a[href]')
                 if 'post.other-publications.global-week-ahead.' in a['href']))[:6]
    if not links:
        raise ValueError('No weekly report links')
    rows = []
    for link in links:
        page = BeautifulSoup(await fetch(client, link), 'html.parser')
        pdfs = [urljoin(link, a['href']) for a in page.select('a[href]')
                if re.search(r'/globalweekahead\d{8}\.pdf$', a['href'])]
        if not pdfs:
            raise ValueError('No weekly report PDF')
        url = pdfs[0]
        # Immutable dated reports already parsed need no repeated download.
        saved = [r for r in previous if r['sourceUrl'] == url]
        rows.extend(saved or parse_scotia(await fetch(client, url, pdf=True), url, retrieved))
    return rows


async def update():
    async with LOCK:
        data = read()
        at = macro.now()
        day = schedule_day(at)
        # A newly enabled adapter receives one initial check, without re-fetching existing sources.
        known = {s['id'] for s in data['sources']}
        versions = {s['id']: s.get('extractionVersion') for s in data['sources']}
        pending = [s for s in SOURCES if data['scheduleDay'] != day or s[0] not in known
                   or (s[0] in ('rbc', 'usbank') and versions.get(s[0]) != institution_forecasts.EXTRACTION_VERSION)]
        if not pending:
            return data
        stamp = macro.iso(at)
        # Persist attempt before I/O so restart cannot create a request loop.
        data.update(scheduleDay=day, lastAttemptAt=stamp)
        write(data)
        pending_ids = {s[0] for s in pending}
        statuses = [s for s in data['sources'] if s['id'] not in pending_ids]
        rows = {r['id']: r for r in data['records']}
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            for name, source_url, label in pending:
                try:
                    if name == 'cleveland':
                        fresh = parse_cleveland(await fetch(client, CLEVELAND), stamp)
                    elif name == 'scotia':
                        fresh = await scotia(client, stamp, data['records'])
                    else:
                        fresh = await institution_forecasts.collect(name, client, stamp)
                    for r in fresh:
                        # Retain first collection time for point-in-time provenance.
                        if r['id'] not in rows:
                            rows[r['id']] = r
                    statuses.append({'id': name, 'label': label, 'url': source_url, 'status': 'ok', 'checkedAt': stamp,
                                     'count': len(fresh), 'error': None, 'extractionVersion': institution_forecasts.EXTRACTION_VERSION})
                except Exception as exc:
                    logging.getLogger(__name__).warning('Public forecast source %s failed: %s', name, type(exc).__name__)
                    statuses.append({'id': name, 'label': label, 'url': source_url, 'status': 'error', 'checkedAt': stamp,
                                     'count': 0, 'extractionVersion': institution_forecasts.EXTRACTION_VERSION,
                                     'error': '公开来源暂不可用或格式变更，保留旧记录并标注状态。'})
        cutoff = (at.date()-timedelta(days=400)).isoformat()
        data.update(records=[r for r in rows.values() if r['sourceUpdatedAt'] >= cutoff], sources=statuses)
        write(data)
        return data


def attach(events, data):
    statuses = {s['id']: s for s in data['sources']}
    for e in events:
        code = EVENT_LABELS.get(e['title'])
        period = e['reference']
        if not re.fullmatch(r'\d{4}-\d{2}', period or ''):
            try:
                period = datetime.strptime((period or '').split(',')[-1].strip(), '%B %Y').strftime('%Y-%m')
            except ValueError:
                continue
        latest = {}
        for r in data['records']:
            if r['indicator'] != code or r['reference'] != period:
                continue
            # Do not attach forecasts published after the event, even if the month matches.
            release = macro.timestamp(e['releaseAt']) if e.get('releaseAt') else None
            if release:
                if r.get('sourceUpdatedTimestamp'):
                    if macro.timestamp(r['sourceUpdatedTimestamp']) >= release:
                        continue
                elif r['sourceUpdatedAt'] >= release.astimezone(macro.ET).date().isoformat():
                    continue  # date-only update cannot prove it preceded a same-day release
            identity = (r['kind'], r['source'])
            if identity not in latest or (r['sourceUpdatedAt'], r['retrievedAt']) > (latest[identity]['sourceUpdatedAt'], latest[identity]['retrievedAt']):
                latest[identity] = r
        e['publicForecasts'] = []
        for r in latest.values():
            age = (macro.now().date()-datetime.fromisoformat(r['sourceUpdatedAt']).date()).days
            state = statuses.get(r['sourceId'], {})
            failed = state.get('status') != 'ok' or (macro.now()-macro.timestamp(state['checkedAt'])).total_seconds() > 2*86400
            historical = bool(e.get('releaseAt') and macro.timestamp(e['releaseAt']) <= macro.now())
            stale = failed or (not historical and age > 14)
            e['publicForecasts'].append({**r, 'stale': stale, 'collectedAfterRelease': bool(e.get('releaseAt') and macro.timestamp(r['retrievedAt']) >= macro.timestamp(e['releaseAt']))})
        choices = [r for r in e['publicForecasts'] if r['kind'] == 'consensus' and not r['stale']]
        if not e.get('forecast') and choices:
            selected = max(choices, key=lambda r: r['sourceUpdatedAt'])
            e.update(forecast=selected['metric'], forecastSource=selected['source'],
                     forecastSourceUrl=selected['sourceUrl'], forecastUpdatedAt=selected['sourceUpdatedAt'])
            e['forecastCollectedAfterRelease'] = selected['collectedAfterRelease']
        e['institutionComparison'] = compare_institutions(e['publicForecasts'])


def compare_institutions(rows):
    # Never count a market survey, model, stale quote or repeated article as another bank.
    banks = {}
    for row in rows:
        if row['kind'] != 'institution' or row.get('stale') or row['metric']['value'] is None:
            continue
        identity = row['sourceId']
        if identity not in banks or (row['sourceUpdatedAt'], row['retrievedAt']) > (banks[identity]['sourceUpdatedAt'], banks[identity]['retrievedAt']):
            banks[identity] = row
    items = list(banks.values())
    if len(items) < 2 or len({r['metric']['unit'] for r in items}) != 1 or len({(r['indicator'],r['reference']) for r in items}) != 1:
        return None
    values = sorted(r['metric']['value'] for r in items)
    unit = items[0]['metric']['unit']
    return {'count': len(items), 'min': macro.metric(str(values[0]), unit),
            'max': macro.metric(str(values[-1]), unit), 'median': macro.metric(str(median(values)), unit),
            'spread': {'value': round(values[-1]-values[0], 8), 'unit': '百分点' if unit == '%' else '人'},
            'earliestUpdate': min(r['sourceUpdatedAt'] for r in items),
            'latestUpdate': max(r['sourceUpdatedAt'] for r in items),
            'recordIds': [r['id'] for r in items]}


def status(data):
    return {'lastAttemptAt': data['lastAttemptAt'], 'sources': data['sources'],
            'schedule': '每天 08:00 Australia/Sydney；后端运行时自动检查，停机后启动补查',
            'recordCount': len(data['records'])}


async def background():
    while True:
        try:
            await update()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception('Public forecast update failed')
        await asyncio.sleep(60)
