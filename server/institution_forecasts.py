"""Conservative extraction of explicit house forecasts from public bank commentary.
Unsupported prose stays missing. No LLM inference, consensus substitution or paid calls.
"""
from datetime import datetime
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

RBC = 'https://www.rbc.com/en/economics/category/us-week-ahead/'
USBANK = 'https://www.usbank.com/corporate-and-commercial-banking/insights/economy/outlook/weekly.html'
EXTRACTION_VERSION = 2
MONTH = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
NUMBER = r'([+-]?\d+(?:\.\d+)?)'
RATE = r'(m/m|month-over-month(?:\s*\(MoM\))?|MoM|y/y|year-over-year(?:\s*\(YoY\))?|YoY)'
INDEX = r'((?:headline\s+|core\s+)?(?:CPI|PCE)(?:\s+price index)?)'
VERB = r'(?:to\s+(?:rise|increase|grow)|(?:rose|rise|increase|grew|grow))'


def period(month, published):
    m = datetime.strptime(month, '%B').month
    anchor = datetime.fromisoformat(published[:10])
    candidates = [datetime(anchor.year+d, m, 1) for d in (-1,0,1)]
    chosen = min(candidates,key=lambda d: abs((d-anchor).days))
    if abs((chosen-anchor).days)>75:
        raise ValueError('Ambiguous forecast horizon')
    return chosen.strftime('%Y-%m')


def code(index, rate):
    return ('core_' if 'core' in index.lower() else '')+('pce' if 'pce' in index.lower() else 'cpi')+('_yoy' if rate.lower().startswith(('y/y','year','yoy')) else '_mom')


def parse_bank(html, url, retrieved, source_id):
    from . import macro, public_forecasts as p
    soup=BeautifulSoup(html,'html.parser')
    if source_id not in ('rbc','usbank') or not soup.find('h1'):
        raise ValueError('Unexpected bank article')
    meta=soup.find('meta',property='article:modified_time')
    published=soup.find('meta',property='article:published_time')
    stamp=(meta or published)
    if not stamp or not stamp.get('content'):
        raise ValueError('Missing article update date')
    updated=macro.timestamp(stamp['content'])
    if updated>macro.timestamp(retrieved):
        raise ValueError('Future article date')
    publication=published['content'] if published else stamp['content']
    name={'rbc':'RBC Economics','usbank':'U.S. Bank Economic Research Group'}[source_id]
    rows=[]
    # Paragraph-only extraction excludes navigation, related article cards and image alt text.
    paragraphs=[' '.join(n.get_text(' ',strip=True).replace('−','-').split()) for n in soup.select('p')
                if not n.find_parent('article') and not n.find_parent(['header','footer','nav'])]
    previous_primary=None
    def add(indicator, ref, amount, paragraph):
        row=p.record(indicator,ref,amount,'institution',name,url,updated.date().isoformat(),retrieved,source_id=source_id)
        if row:
            row.update(sourcePublishedAt=publication[:10], sourceUpdatedTimestamp=stamp['content'],
                       evidenceHash=macro.digest(paragraph), extraction='explicit-bank-forecast')
            # Short verbatim evidence only; no generated explanation attributed to the bank.
            words = paragraph.split()
            row['institutionView'] = {
                'kind': 'source_excerpt', 'language': 'en',
                'excerpt': ' '.join(words[:25]) + (' …' if len(words) > 25 else ''),
                'truncated': len(words) > 25, 'publishedAt': publication,
                'updatedAt': stamp['content'], 'collectedAt': retrieved,
                'sourceUrl': url, 'extractionVersion': EXTRACTION_VERSION,
            }
            # A change in prose is a new evidence version even if the forecast is unchanged.
            row['id'] = macro.digest([row['id'], row['evidenceHash']])
            rows.append(row)
    for paragraph in paragraphs:
        this_primary=None
        # Shared headline/core forecast must explicitly identify CPI and monthly basis.
        both=re.search(r'For CPI, we expect to see both headline and core inflation '+VERB+r' '+NUMBER+r'% '+RATE+r' in '+MONTH,paragraph,re.I)
        if both:
            ref=period(both[3],publication)
            for label in ['CPI','core CPI']:add(code(label,both[2]),ref,both[1],paragraph)
        # Explicit named index, forecast verb, numeric value, basis and statistical month.
        pattern=r'(?:We (?:expect|forecast) (?:the )?'+INDEX+r' '+VERB+r'|'+INDEX+r' is expected to (?:rise|increase|grow)) '+NUMBER+r'% '+RATE+r' in '+MONTH
        for m in re.finditer(pattern,paragraph,re.I):
            if not m[1]:
                continue  # Bare "is expected" may describe a survey rather than this bank's view.
            label=m[1] or m[2];ref=period(m[5],publication);indicator=code(label,m[4])
            add(indicator,ref,m[3],paragraph)
            this_primary=(label,ref,m[4])
            # Only a forecast-linked annual pace in the same sentence may be paired.
            tail=re.split(r'(?<=[.!?])\s+(?=[A-Z])',paragraph[m.end():],maxsplit=1)[0]
            annual=re.match(r', (?:pushing|lifting) the y/y pace (?:up )?to '+NUMBER+r'%',tail,re.I)
            if annual:add(code(label,'y/y'),ref,annual[1],paragraph)
            # U.S. Bank may put core CPI in the same sentence and state the basis only once.
            core=re.search(r',? while core CPI is expected to (?:increase|rise) '+NUMBER+r'% for a second consecutive month',tail,re.I)
            if core and label.lower() in ('cpi','headline cpi') and indicator=='cpi_mom':
                add('core_cpi_mom',ref,core[1],paragraph)
        # RBC's adjacent paragraph may explicitly continue with headline PCE.
        continuation=re.match(r'Headline is expected to rise '+NUMBER+r'% m/m, with the y/y pace accelerating to '+NUMBER+r'%',paragraph,re.I)
        if continuation and previous_primary and 'pce' in previous_primary[0].lower():
            add('pce_mom',previous_primary[1],continuation[1],paragraph)
            add('pce_yoy',previous_primary[1],continuation[2],paragraph)
        jobs=re.search(r'We forecast '+NUMBER+r'(K|,000)? jobs were added to payrolls in '+MONTH,paragraph,re.I)
        if jobs:
            # record() accepts payrolls in thousands, matching the source adapter convention.
            thousands=float(jobs[1]) if jobs[2] else float(jobs[1])/1000
            add('nfp',period(jobs[3],publication),str(thousands),paragraph)
        previous_primary=this_primary
    # Conflicting numbers for one indicator/period in one article are ambiguous: omit, never choose silently.
    by_key={}
    for row in rows:by_key.setdefault((row['indicator'],row['reference']),[]).append(row)
    return [matches[0] for matches in by_key.values() if len({r['metric']['value'] for r in matches})==1]


async def collect(source_id,client,retrieved):
    from . import public_forecasts as p
    if source_id=='usbank':
        return parse_bank(await p.fetch(client,USBANK),USBANK,retrieved,source_id)
    soup=BeautifulSoup(await p.fetch(client,RBC),'html.parser')
    links=list(dict.fromkeys(urljoin(RBC,a['href']) for a in soup.select('a[href]')
               if a['href'].startswith('https://www.rbc.com/en/economics/us-week-ahead/')))[:6]
    if not links:raise ValueError('Missing RBC week-ahead links')
    rows=[]
    for url in links:
        rows.extend(parse_bank(await p.fetch(client,url),url,retrieved,source_id))
    return rows
