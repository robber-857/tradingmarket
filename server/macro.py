"""Public-source macro calendar; optional consensus feed. No synthetic economic values."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import os
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dotenv import dotenv_values
import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .sec import ROOT

UTC = timezone.utc
ET = ZoneInfo('America/New_York')
CACHE = ROOT / 'server' / 'cache' / 'macro'
SNAPSHOTS = ROOT / 'server' / 'macro_snapshots'
CACHE.mkdir(parents=True, exist_ok=True)
SNAPSHOTS.mkdir(exist_ok=True)
LOCK = asyncio.Lock()
BLS_SCHEDULE = 'https://www.bls.gov/schedule/news_release/bls.ics'
BEA_SCHEDULE = 'https://www.bea.gov/news/schedule'
FED_SCHEDULE = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
BEA_PCE = 'https://www.bea.gov/data/personal-consumption-expenditures-price-index'
BLS_API = 'https://api.bls.gov/publicAPI/v1/timeseries/data/'
DOL_DATA = 'https://www.dol.gov/newsroom/economicdata'
TE_DOCS = 'https://docs.tradingeconomics.com/economic_calendar/schema/'
SERIES = ['CUSR0000SA0', 'CUUR0000SA0', 'CUSR0000SA0L1E', 'CUUR0000SA0L1E', 'CES0000000001']


class MacroError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def now():
    return datetime.now(UTC)


def key():
    return (dotenv_values(ROOT / '.env').get('TRADING_ECONOMICS_API_KEY', os.getenv('TRADING_ECONOMICS_API_KEY', '')) or '').strip()


def safe_url(url, fallback):
    p = urlparse(str(url or ''))
    allowed = ('bls.gov', 'bea.gov', 'federalreserve.gov', 'tradingeconomics.com', 'dol.gov')
    return str(url) if p.scheme in ('http', 'https') and not p.username and not p.password and any(p.hostname == d or (p.hostname or '').endswith('.' + d) for d in allowed) else fallback


def timestamp(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (d.replace(tzinfo=UTC) if d.tzinfo is None else d).astimezone(UTC)


def iso(d):
    return d.astimezone(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def metric(value, unit):
    """Only scalar values with explicit compatible units participate in arithmetic."""
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip().replace('−', '-')
    if raw.lower() in ('', '-', 'n/a', 'na', 'null', '.'):
        return None
    m = re.fullmatch(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*([KMB%]?)', raw, re.I)
    numeric = None
    if m:
        suffix = m[2].upper()
        if (unit == '%' and suffix in ('', '%')) or (unit == '人' and suffix in ('', 'K', 'M', 'B')):
            numeric = float(Decimal(m[1].replace(',', '')) * {'': 1, '%': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000}[suffix])
    display = raw + ('%' if unit == '%' and m and not m[2] else '')
    if unit == '人' and numeric is not None:
        display = f'{numeric:,.0f} 人'
    return {'display': display[:80], 'value': numeric, 'unit': unit}


def event(group, title, release, reference, source, url, *, precision='confirmed', event_id=None):
    return {'id': event_id or digest([group, title, release, reference]), 'group': group, 'title': title,
            'releaseAt': release, 'timePrecision': precision, 'reference': reference,
            'previous': None, 'previousBeforeRevision': None, 'forecast': None, 'actual': None,
            'surprise': None, 'source': source, 'sourceUrl': url, 'provider': source,
            'retrievedAt': iso(now()), 'stale': False, 'note': '', 'valueBasis': '发布机构披露',
            'forecastSource': None, 'providerUpdatedAt': None}


def finalize(e):
    release = timestamp(e['releaseAt']) if e['releaseAt'] else None
    # Future actuals are never exposed, even if a provider returns contradictory data.
    if release and release > now():
        if e['actual'] is not None:
            e['note'] += ' 供应商返回了未来事件的公布值，已隐藏，等待发布时间核验。'
        e['actual'] = None
    e['status'] = 'released' if e['actual'] is not None else 'upcoming' if release and release > now() else 'pending'
    a, f = e['actual'], e['forecast']
    if a and f and a['value'] is not None and f['value'] is not None and a['unit'] == f['unit']:
        delta = round(a['value'] - f['value'], 8)
        e['surprise'] = {'value': delta, 'unit': '百分点' if a['unit'] == '%' else a['unit'],
                         'display': f'{delta:+g} ' + ('个百分点' if a['unit'] == '%' else a['unit'])}
    else:
        e['surprise'] = None
    e['snapshotId'] = digest({k: v for k, v in e.items() if k != 'snapshotId'})
    path = SNAPSHOTS / (e['snapshotId'] + '.json')
    if not path.exists():
        path.write_text(json.dumps(e, ensure_ascii=False), encoding='utf-8')
    return e


async def cached(name, url, *, body=None, headers=None, ttl=900, max_age=86400, pdf=False):
    """Cache only successful responses. Credentials never appear in URL/cache/exception."""
    path = CACHE / (name + '.json')
    previous = None
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
        age = (now() - timestamp(previous['retrievedAt'])).total_seconds()
        if 0 <= age < ttl:
            return previous['body'], previous['retrievedAt'], False
    except (OSError, ValueError, KeyError, TypeError):
        previous = None
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            r = await client.request('POST' if body is not None else 'GET', url, json=body, headers=headers)
        if r.status_code in (401, 403):
            raise MacroError(503, '数据源拒绝访问；请检查接口权限或稍后重试。')
        if r.status_code == 429:
            raise MacroError(429, '数据源请求额度受限，请稍后刷新。')
        r.raise_for_status()
        # BLS sends quota failures as HTTP 200; don't overwrite a good cache.
        if url == BLS_API and r.json().get('status') != 'REQUEST_SUCCEEDED':
            raise MacroError(503, 'BLS API 暂未返回有效序列，可能达到免费请求额度。')
        text = r.text
        if pdf:
            if not r.content.startswith(b'%PDF') or len(r.content) > 12_000_000:
                raise ValueError('Invalid source PDF')
            text = '\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(r.content)).pages[:5])
        stamp = iso(now())
        path.write_text(json.dumps({'body': text, 'retrievedAt': stamp}), encoding='utf-8')
        return text, stamp, False
    except (httpx.HTTPError, MacroError, ValueError, PdfReadError) as exc:
        if previous and 0 <= (now() - timestamp(previous['retrievedAt'])).total_seconds() <= max_age:
            return previous['body'], previous['retrievedAt'], True
        if isinstance(exc, MacroError):
            raise exc
        raise MacroError(503, '数据源暂时不可用，没有可用的近期缓存。') from None


def provenance(events, stamp, stale):
    for e in events:
        e.update(retrievedAt=stamp, stale=stale)
    return events


def parse_bls_schedule(text):
    if 'BEGIN:VCALENDAR' not in text:
        raise ValueError('Invalid BLS calendar')
    text = re.sub(r'\r?\n[ \t]', '', text)
    out = []
    for block in text.split('BEGIN:VEVENT')[1:]:
        fields = {}
        for line in block.splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                fields[k] = v
        title = fields.get('SUMMARY', '')
        group = 'CPI' if 'Consumer Price Index' in title else 'NFP' if 'Employment Situation' in title else None
        if not group:
            continue
        start = next(((k, v) for k, v in fields.items() if k.startswith('DTSTART')), None)
        if not start:
            continue
        k, v = start
        dt = datetime.strptime(v.rstrip('Z'), '%Y%m%dT%H%M%S')
        tz = UTC if v.endswith('Z') else ZoneInfo(k.split('TZID=')[-1]) if 'TZID=' in k else ET
        out.append(event(group, 'CPI 发布' if group == 'CPI' else '非农就业报告', iso(dt.replace(tzinfo=tz)), title,
                         'BLS', BLS_SCHEDULE))
    if not out:
        raise ValueError('BLS schedule mapping empty')
    return out


def parse_bea_schedule(text):
    soup = BeautifulSoup(text, 'html.parser')
    out = []
    for table in soup.find_all('table'):
        match = re.search(r'Year\s+(\d{4})', table.get_text(' ', strip=True))
        if not match:
            continue
        for row in table.select('tr'):
            title, day, clock = row.select_one('.release-title'), row.select_one('.release-date'), row.select_one('small')
            if not (title and day and clock) or 'Personal Income and Outlays' not in title.get_text():
                continue
            dt = datetime.strptime(f'{day.get_text(strip=True)} {match[1]} {clock.get_text(strip=True)}', '%B %d %Y %I:%M %p').replace(tzinfo=ET)
            out.append(event('PCE', 'PCE 物价与个人收支', iso(dt), title.get_text(' ', strip=True), 'BEA', BEA_SCHEDULE))
    if not out:
        raise ValueError('BEA schedule mapping empty')
    return out


def parse_fed_schedule(text):
    soup = BeautifulSoup(text, 'html.parser')
    out = []
    for panel in soup.select('.panel'):
        h = panel.select_one('.panel-heading')
        match = re.search(r'(\d{4}) FOMC Meetings', h.get_text(' ', strip=True) if h else '')
        if not match:
            continue
        for row in panel.select('.fomc-meeting'):
            month, days = row.select_one('.fomc-meeting__month'), row.select_one('.fomc-meeting__date')
            if not month or not days or not re.fullmatch(r'\d+(?:-\d+)?\*?', days.get_text(strip=True)):
                continue  # irregular/emergency/cross-month rows require explicit mapping
            try:
                dt = datetime.strptime(f'{month.get_text(strip=True)} {re.findall(r"\d+", days.get_text())[-1]} {match[1]}', '%B %d %Y').replace(tzinfo=ET)
            except ValueError:
                continue
            links = [a['href'] for a in row.select('a[href]') if re.fullmatch(r'/newsevents/pressreleases/monetary\d{8}a.htm', a['href'])]
            e = event('FOMC', 'FOMC 利率决议', iso(dt), days.get_text(strip=True), 'Federal Reserve',
                      urljoin(FED_SCHEDULE, links[0]) if links else FED_SCHEDULE, precision='date-only')
            e['note'] = '官网会议日历仅确认决议日期；时刻以决议公告为准。'
            out.append(e)
    if not out:
        raise ValueError('Fed schedule mapping empty')
    return out


def bls_observations(payload):
    """Latest-vintage calculations, explicitly NOT an initial-release archive."""
    if payload.get('status') != 'REQUEST_SUCCEEDED':
        raise ValueError('BLS response failed')
    by_id = {}
    for s in payload['Results']['series']:
        points = {}
        for r in s['data']:
            if re.fullmatch(r'M(0[1-9]|1[0-2])', r['period']):
                try:
                    points[f'{r["year"]}-{r["period"][1:]}'] = Decimal(r['value'])
                except InvalidOperation:
                    pass
        by_id[s['seriesID']] = points
    out = []
    definitions = [(SERIES[0], 'CPI 环比（季调）', 1), (SERIES[1], 'CPI 同比（未季调）', 12),
                   (SERIES[2], '核心 CPI 环比（季调）', 1), (SERIES[3], '核心 CPI 同比（未季调）', 12),
                   (SERIES[4], '非农就业月增量（季调）', 1)]
    def shift(period, n):
        y, m = map(int, period.split('-'))
        index = y * 12 + m - 1 - n
        return f'{index // 12:04d}-{index % 12 + 1:02d}'
    for sid, title, lag in definitions:
        points = by_id.get(sid, {})
        if not points:
            continue
        latest = max(points)
        group, unit = ('NFP', '人') if sid == SERIES[4] else ('CPI', '%')
        def calculate(period):
            current, base = points.get(period), points.get(shift(period, lag))
            if current is None or base is None or (group == 'CPI' and base <= 0):
                return None
            value = (current - base) * 1000 if group == 'NFP' else (current / base - 1) * 100
            return metric(f'{value:.0f}' if group == 'NFP' else f'{value:.1f}', unit)
        e = event(group, title, None, latest, 'BLS Public Data API', f'https://data.bls.gov/timeseries/{sid}', precision='unknown')
        e.update(actual=calculate(latest), previous=calculate(shift(latest, 1)), seriesId=sid,
                 valueBasis='当前修订版本的序列计算值；不是首发值',
                 note='发布时间未从 API 核验。环比按相邻月份计算，同比严格比较去年同月；缺月不跨月补算。')
        out.append(e)
    if not out:
        raise ValueError('BLS mapping empty')
    return out


def parse_bea_release(text, url):
    soup = BeautifulSoup(text, 'html.parser')
    stamp = soup.select_one('.field--name-field-release-date')
    match = re.search(r'(\w+ \d{1,2}, \d{4})', stamp.get_text() if stamp else '')
    clock = re.search(r'(\d{1,2}:\d{2})\s*([ap])\.m\.', stamp.get_text() if stamp else '', re.I)
    title = next((h.get_text(' ', strip=True) for h in soup.select('h1') if 'Personal Income and Outlays,' in h.get_text()), '')
    if not match or not clock or not title:
        raise ValueError('BEA release header changed')
    release = datetime.strptime(f'{match[1]} {clock[1]} {clock[2].upper()}M', '%B %d, %Y %I:%M %p').replace(tzinfo=ET)
    out = []
    for table in soup.select('table'):
        if 'Percent change from preceding month' not in table.get_text():
            continue
        for row in table.select('tr'):
            cells = [c.get_text(' ', strip=True) for c in row.find_all(['td', 'th'])]
            if len(cells) != 3 or cells[0] not in ('PCE price index', 'PCE price index excluding food and energy'):
                continue
            e = event('PCE', '核心 PCE 环比' if 'excluding' in cells[0] else 'PCE 环比', iso(release), title.split(',', 1)[1].strip(), 'BEA', url)
            e.update(previous=metric(cells[1], '%'), actual=metric(cells[2], '%'), valueBasis='该期 BEA 新闻稿月度表；前值为本次发布所列版本')
            out.append(e)
    if len(out) != 2:
        raise ValueError('BEA release table changed')
    return out


def parse_fed_rate(text):
    plain = BeautifulSoup(text, 'html.parser').get_text(' ', strip=True)
    number_pattern = r'(\d+(?:\.\d+)?(?:[ -]\d+/\d+)?|\d+/\d+)'
    match = re.search(r'target range for the federal funds rate (?:by [\d/ .-]+ percentage points? )?(?:at|to) ' + number_pattern + ' to ' + number_pattern + ' percent', plain, re.I)
    if not match:
        return None
    def number(s):
        parts = re.split('[ -]', s)
        return float(Fraction(parts[0]) + (Fraction(parts[1]) if len(parts) > 1 else 0))
    low, high = number(match[1]), number(match[2])
    if not 0 <= low <= high <= 30:
        return None
    return {'display': f'{low:g}–{high:g}%', 'value': None, 'unit': '%', 'lower': low, 'upper': high}


def parse_bls_pdf(text, url, group):
    text = ' '.join(text.split())
    first = re.search(r'(\d{1,2}:\d{2}) a\.m\. \(ET\) \w+, (\w+ \d{1,2}, \d{4})', text[:450])
    heading = 'CONSUMER PRICE INDEX' if group == 'CPI' else 'THE EMPLOYMENT SITUATION'
    period = re.search(heading + r'\s*[–—-]\s*([A-Z]+ \d{4})', text[:650])
    upcoming = re.search(r'for (\w+ \d{4}) is scheduled to be published on \w+, (\w+ \d{1,2}, \d{4}), at (\d{1,2}:\d{2}) a\.m\. \(ET\)', text)
    if not first or not period:
        raise ValueError('BLS release header changed')
    title = 'CPI 发布' if group == 'CPI' else '非农就业报告'
    def dt(day, clock):
        return iso(datetime.strptime(f'{day} {clock}', '%B %d, %Y %H:%M').replace(tzinfo=ET))
    ref = datetime.strptime(period[1].title(), '%B %Y').strftime('%Y-%m')
    current = event(group, title, dt(first[2], first[1]), ref, 'BLS / 美国劳工部', url)
    result = [current]
    if upcoming:
        next_ref = datetime.strptime(upcoming[1], '%B %Y').strftime('%Y-%m')
        result.append(event(group, title, dt(upcoming[2], upcoming[3]), next_ref, 'BLS / 美国劳工部', url))
    return result


TE_NAMES = {
    'inflation rate yoy': ('CPI', 'CPI 同比'), 'inflation rate mom': ('CPI', 'CPI 环比'),
    'core inflation rate yoy': ('CPI', '核心 CPI 同比'), 'core inflation rate mom': ('CPI', '核心 CPI 环比'),
    'non farm payrolls': ('NFP', '非农就业月增量'), 'nonfarm payrolls': ('NFP', '非农就业月增量'),
    'pce price index mom': ('PCE', 'PCE 环比'), 'pce price index yoy': ('PCE', 'PCE 同比'),
    'core pce price index mom': ('PCE', '核心 PCE 环比'), 'core pce price index yoy': ('PCE', '核心 PCE 同比'),
    'fed interest rate decision': ('FOMC', 'FOMC 利率决议（供应商报价口径）'),
}


def normalize_te(rows):
    if not isinstance(rows, list):
        raise ValueError('Invalid calendar response')
    if len(rows) >= 1000:
        raise ValueError('Potentially truncated calendar; use a shorter window')
    out = []
    for row in rows:
        if not isinstance(row, dict) or row.get('Country') != 'United States':
            continue
        name = re.sub(r'\s*\([^)]*\)\s*$', '', str(row.get('Event', ''))).strip().lower()
        if name not in TE_NAMES:
            continue
        if not (row.get('CalendarId') or row.get('CalendarID')):
            raise ValueError('Calendar event identity missing')
        group, title = TE_NAMES[name]
        release = iso(timestamp(row['Date']))
        unit = '人' if group == 'NFP' else '%'
        e = event(group, title, release, str(row.get('Reference') or ''), str(row.get('Source') or 'Trading Economics'),
                  safe_url(row.get('SourceURL'), TE_DOCS), precision='confirmed' if str(row.get('DateSpan')) == '0' else 'estimated',
                  event_id='te-' + str(row.get('CalendarId') or row.get('CalendarID')))
        e.update(provider='Trading Economics', previous=metric(row.get('Previous'), unit),
                 previousBeforeRevision=metric(row.get('Revised'), unit), forecast=metric(row.get('Forecast'), unit),
                 actual=metric(row.get('Actual'), unit), forecastSource='Trading Economics 经济学家调查',
                 providerUpdatedAt=row.get('LastUpdate'), valueBasis='供应商转引官方发布；Previous 为修订后前值',
                 note='不使用 TEForecast 代替市场一致预期。' + (' 政策利率报价不自动等同于完整目标区间。' if group == 'FOMC' else ''))
        out.append(e)
    return out


async def public_events(start, end):
    events, warnings, sources = [], [], []
    async def schedule(name, url, parser):
        try:
            text, stamp, stale = await cached(name, url, ttl=3600, max_age=7*86400)
            parsed = provenance(parser(text), stamp, stale)
            sources.append({'name': name, 'available': True, 'stale': stale, 'retrievedAt': stamp, 'url': url})
            return parsed
        except (MacroError, ValueError, KeyError, TypeError):
            warnings.append(f'{name} 官方排期暂不可用；缺失日期不会按惯例推算。')
            sources.append({'name': name, 'available': False, 'url': url})
            return []
    bls, bea, fed = await asyncio.gather(schedule('BLS', BLS_SCHEDULE, parse_bls_schedule),
        schedule('BEA', BEA_SCHEDULE, parse_bea_schedule), schedule('FOMC', FED_SCHEDULE, parse_fed_schedule))
    events.extend(bls + bea)
    # Latest-vintage BLS observations are separate from the date-filtered release archive.
    observations = []
    try:
        year = now().year
        raw, stamp, stale = await cached('bls-series', BLS_API, body={'seriesid': SERIES, 'startyear': str(year-2), 'endyear': str(year)}, ttl=3600, max_age=86400)
        observations = provenance(bls_observations(json.loads(raw)), stamp, stale)
    except (MacroError, ValueError, KeyError, TypeError):
        warnings.append('BLS 最新序列暂不可用，CPI / 非农公布值未补造。')
    # DOL republishes original BLS PDFs, including exact current and next release times.
    # This is an official public source, useful when BLS's calendar is unavailable.
    try:
        raw, _, index_stale = await cached('dol-index', DOL_DATA, ttl=900)
        soup = BeautifulSoup(raw, 'html.parser')
        for group, prefix in [('CPI', 'cpi'), ('NFP', 'empsit')]:
            links = [a['href'] for a in soup.select('a[href]') if re.fullmatch(fr'/newsroom/economicdata/{prefix}_\d{{8}}\.pdf', a['href'])]
            if not links:
                warnings.append(f'{group} 官方 PDF 链接暂不可用。')
                continue
            url = 'https://www.dol.gov' + links[0]
            raw, stamp, stale = await cached('dol-pdf-' + digest(url), url, pdf=True, ttl=3600, max_age=7*86400)
            stale = stale or index_stale
            releases = provenance(parse_bls_pdf(raw, url, group), stamp, stale)
            current = releases[0]
            matched = [o for o in observations if o['group'] == group and o['reference'] == current['reference']]
            if matched:
                for o in matched:
                    o.update(releaseAt=current['releaseAt'], timePrecision='confirmed', releaseSourceUrl=url, stale=o['stale'] or stale)
                    o['note'] = '发布时间来自劳工部转载的 BLS 原始新闻稿；数值为当前 API 修订版本。'
                    events.append(o)
                    observations.remove(o)
                releases = releases[1:]
            for release in releases:
                # Do not duplicate entries already supplied by the official ICS.
                if not any(e['group'] == group and e['releaseAt'] == release['releaseAt'] for e in events):
                    events.append(release)
    except (MacroError, ValueError, KeyError, TypeError):
        warnings.append('劳工部转载的 BLS 发布时间暂无法核验；最新序列仍单独展示。')
    try:
        text, _, index_stale = await cached('bea-pce-page', BEA_PCE, ttl=900)
        soup = BeautifulSoup(text, 'html.parser')
        link = next(a['href'] for a in soup.select('a[href]') if a.get_text(strip=True) == 'Current Release')
        url = safe_url(urljoin(BEA_PCE, link), '')
        if urlparse(url).hostname != 'www.bea.gov' or not urlparse(url).path.startswith('/news/'):
            raise ValueError('Unexpected release link')
        raw, stamp, stale = await cached('bea-release-' + digest(url), url, ttl=900)
        events.extend(provenance(parse_bea_release(raw, url), stamp, stale or index_stale))
    except (MacroError, ValueError, KeyError, TypeError, StopIteration):
        warnings.append('BEA 最新新闻稿无法完整解析；不会用个人消费支出增速冒充 PCE 通胀。')
    # Retrieve the previous statement too, so a range comparison has a genuine source.
    dated = sorted(fed, key=lambda e: e['releaseAt'])
    relevant = [i for i, e in enumerate(dated) if start <= timestamp(e['releaseAt']).astimezone(ET).date() <= end]
    indices = sorted(set(relevant + [i-1 for i in relevant if i > 0]))
    for i in indices:
        e = dated[i]
        if e['sourceUrl'] == FED_SCHEDULE:
            continue
        try:
            text, stamp, stale = await cached('fed-release-' + digest(e['sourceUrl']), e['sourceUrl'], ttl=3600)
            e['actual'] = parse_fed_rate(text)
            e.update(retrievedAt=stamp, stale=stale)
            plain = BeautifulSoup(text, 'html.parser').get_text(' ', strip=True)
            clock = re.search(r'For release at (\d{1,2}):(\d{2}) ([ap])\.m\.', plain, re.I)
            if clock:
                local = timestamp(e['releaseAt']).astimezone(ET)
                hour = int(clock[1]) % 12 + (12 if clock[3].lower() == 'p' else 0)
                e.update(releaseAt=iso(local.replace(hour=hour, minute=int(clock[2]))), timePrecision='confirmed', note='目标利率区间来自官方声明；未读取发布会或点阵图。')
            if not e['actual']:
                warnings.append('部分 FOMC 声明的利率区间无法解析，请查看原文。')
        except (MacroError, ValueError):
            warnings.append('部分 FOMC 声明暂不可用。')
    for i in relevant:
        e = dated[i]
        if i > 0 and dated[i-1]['actual']:
            e['previous'] = dated[i-1]['actual']
            e['previousSourceUrl'] = dated[i-1]['sourceUrl']
            e['stale'] = e['stale'] or dated[i-1]['stale']
        events.append(e)
    return events, observations, warnings, sources


async def calendar(start=None, end=None):
    today = now().astimezone(ET).date()
    start, end = start or today - timedelta(days=30), end or today + timedelta(days=60)
    if start > end or (end-start).days > 120:
        raise MacroError(422, '日期范围须按先后排列，且不超过 120 天。')
    async with LOCK:
        events, observations, warnings, sources = await public_events(start, end)
        # Expand future CPI/PCE bundles into comparable measures. Fill a previous
        # value only when the statistic and the immediately preceding month match.
        expanded = []
        for e in events:
            if e['actual'] is not None or timestamp(e['releaseAt']) <= now() or e['group'] == 'FOMC':
                expanded.append(e)
                continue
            candidates = [x for x in events if x['group'] == e['group'] and x['actual'] is not None]
            try:
                ref = e['reference']
                if not re.fullmatch(r'\d{4}-\d{2}', ref):
                    ref = datetime.strptime(ref.split(',')[-1].strip(), '%B %Y').strftime('%Y-%m')
                prior = (datetime.strptime(ref, '%Y-%m').date() - timedelta(days=1)).strftime('%Y-%m')
                matching = [x for x in candidates if (x['reference'] if re.fullmatch(r'\d{4}-\d{2}', x['reference']) else datetime.strptime(x['reference'], '%B %Y').strftime('%Y-%m')) == prior]
            except ValueError:
                matching = []
            if matching:
                for previous in matching:
                    item = {**e, 'title': previous['title'], 'previous': previous['actual'],
                            'previousSourceUrl': previous['sourceUrl'],
                            'valueBasis': '待公布；前值沿用相邻统计期的已取得数据版本',
                            'stale': e['stale'] or previous['stale']}
                    item['id'] = digest([item['group'], item['title'], item['releaseAt'], item['reference']])
                    expanded.append(item)
            else:
                expanded.append(e)
        events = expanded
        provider_state = 'not_configured'
        if key():
            try:
                url = f'https://api.tradingeconomics.com/calendar/country/united%20states/{start}/{end}?f=json'
                raw, stamp, stale = await cached(f'te-{start}-{end}-{digest(key())}', url, headers={'Authorization': key()}, ttl=60)
                te = provenance(normalize_te(json.loads(raw)), stamp, stale)
                # Provider rows replace only matching group/date; unrelated official dates remain.
                covered = {(e['group'], timestamp(e['releaseAt']).astimezone(ET).date()) for e in te}
                events = [e for e in events if (e['group'], timestamp(e['releaseAt']).astimezone(ET).date()) not in covered] + te
                provider_state = 'stale' if stale else 'connected'
                if not te:
                    warnings.append('一致预期接口未返回本窗口内四类美国指标；可能没有覆盖或账户权限不足。')
            except (MacroError, ValueError, KeyError, TypeError):
                provider_state = 'unavailable'
                warnings.append('可选一致预期接口不可用，继续显示官方数据。请检查权限、额度或网络。')
        events = [e for e in events if start <= timestamp(e['releaseAt']).astimezone(ET).date() <= end]
        events.sort(key=lambda e: (e['releaseAt'], e['title']))
        events = [finalize(e) for e in events]
        observations = [finalize(e) for e in observations]
        return {'events': events, 'observations': observations, 'from': str(start), 'to': str(end),
                'rangeTimezone': 'America/New_York', 'checkedAt': iso(now()), 'sources': sources,
                'warnings': list(dict.fromkeys(warnings)), 'consensusStatus': provider_state,
                'notice': '免费官方来源不提供市场一致预期。最新序列可能已修订，不是历史首发数据库。页面打开时每分钟检查，官方源缓存按各源频率更新；不保证秒级推送。'}


def load_snapshot(snapshot_id):
    if not re.fullmatch(r'[0-9a-f]{24}', snapshot_id):
        raise MacroError(422, '无效事件快照。')
    try:
        e = json.loads((SNAPSHOTS / (snapshot_id + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise MacroError(409, '事件快照不存在，请刷新日历。') from None
    if (now() - timestamp(e['retrievedAt'])).total_seconds() > 7*86400:
        raise MacroError(409, '事件快照已过期，请刷新日历后重新分析。')
    return e
