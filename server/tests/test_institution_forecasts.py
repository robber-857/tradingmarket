import asyncio
from datetime import datetime, timezone

import pytest
from server import institution_forecasts as bank, public_forecasts as p, macro

STAMP='2026-11-10T01:00:00Z'
URL='https://www.rbc.com/en/economics/us-week-ahead/test/'

def html(*paragraphs, updated='2026-11-09T18:00:00Z', published='2026-11-05T18:00:00Z'):
    return f'<h1>US Week Ahead</h1><meta property="article:modified_time" content="{updated}"><meta property="article:published_time" content="{published}">'+''.join('<p>'+t+'</p>' for t in paragraphs)


def parse(*paragraphs,source='rbc',**kwargs):
    return bank.parse_bank(html(*paragraphs,**kwargs),URL,STAMP,source)


def test_explicit_shared_cpi_and_usbank_core():
    rows=parse('For CPI, we expect to see both headline and core inflation rose +0.3% m/m in October.')
    assert {r['indicator'] for r in rows}=={'cpi_mom','core_cpi_mom'}
    assert all(r['sourceId']=='rbc' and r['reference']=='2026-10' for r in rows)
    rows=parse('We expect headline CPI to rise 0.4% month-over-month (MoM) in October, down from 0.6% in September but still elevated, while core CPI is expected to increase 0.3% for a second consecutive month.',source='usbank')
    assert [(r['indicator'],r['metric']['value']) for r in rows]==[('cpi_mom',.4),('core_cpi_mom',.3)]


def test_nfp_and_pce_not_spending_or_wages():
    rows=parse('We forecast 42K jobs were added to payrolls in October and expect the unemployment rate held steady at 4.2%.',
               'We expect average hourly earnings rose +0.3% m/m in October.')
    assert len(rows)==1 and rows[0]['metric']['value']==42000
    rows=parse('We forecast the core PCE price index rose +0.4% m/m in September, pushing the y/y pace up to 3.1%.',
               'Headline is expected to rise 0.5% m/m, with the y/y pace accelerating to 3.7%.',
               'Our forecast calls for a 0.6% m/m increase in personal spending.')
    assert {r['indicator']:r['metric']['value'] for r in rows}=={'core_pce_mom':.4,'core_pce_yoy':3.1,'pce_mom':.5,'pce_yoy':3.7}


def test_missing_month_basis_no_guessing_or_bare_consensus():
    rows=parse('CPI is expected to rise 0.3% m/m in October.',
               'We expect CPI to rise 0.3% in October.',
               'We expect CPI to rise 0.3% m/m.',
               'CPI rose 0.3% m/m in October.',
               'Headline is expected to rise 0.5% m/m, with the y/y pace accelerating to 3.7%.')
    assert rows==[]


def test_conflicting_values_and_future_publication_fail_closed():
    assert parse('We expect CPI to rise 0.3% m/m in October. We forecast CPI to rise 0.4% m/m in October.')==[]
    with pytest.raises(ValueError):parse('We expect CPI to rise 0.3% m/m in October.',updated='2027-01-01T00:00:00Z')
    with pytest.raises(ValueError):bank.parse_bank('<h1>Forecast</h1><p>We expect CPI to rise 0.3% m/m in October.</p>',URL,STAMP,'rbc')


def test_bank_metadata_and_exact_time_before_release(monkeypatch):
    monkeypatch.setattr(macro,'now',lambda:datetime.fromisoformat(STAMP.replace('Z','+00:00')))
    rows=parse('We expect CPI to rise 0.3% m/m in October.',updated='2026-11-09T12:00:00Z')
    assert rows[0]['sourcePublishedAt']=='2026-11-05'
    e=macro.event('CPI','CPI 环比（季调）','2026-11-09T13:30:00Z','2026-10','BLS','https://www.bls.gov')
    d={'records':rows,'sources':[{'id':'rbc','status':'ok','checkedAt':STAMP}]}
    p.attach([e],d)
    assert len(e['publicForecasts'])==1 and e['forecast'] is None
    d['records']=parse('We expect CPI to rise 0.3% m/m in October.',updated='2026-11-09T14:00:00Z')
    p.attach([e],d)
    assert not e['publicForecasts']


def test_source_view_is_verbatim_bounded_and_versions_prose():
    from server import macro_ai
    text = 'We expect CPI to rise 0.3% m/m in October. ' + ' '.join(['Evidence'] * 30)
    first = parse(text)[0]
    view = first['institutionView']
    assert view['kind'] == 'source_excerpt' and view['language'] == 'en'
    assert view['excerpt'] == ' '.join(text.split()[:25]) + ' …'
    assert view['collectedAt'] == STAMP and view['publishedAt'] == '2026-11-05T18:00:00Z'
    second = parse(text + ' Changed reasoning.')[0]
    assert first['metric'] == second['metric'] and first['id'] != second['id']
    assert 'Changed reasoning.' not in first['institutionView']['excerpt']
    e=macro.event('CPI','CPI 环比（季调）','2026-11-10T13:30:00Z','2026-10','BLS','https://www.bls.gov')
    e['publicForecasts']=[first]
    evidence=macro_ai.context_for(e)['registry']['E_VIEW_0']
    assert evidence['kind']=='source_opinion'
    assert evidence['retrievedAt']==view['collectedAt']
    assert evidence['display']==view['excerpt']


def test_existing_bank_adapter_upgrades_once(monkeypatch, tmp_path):
    monkeypatch.setattr(p, 'STORE', tmp_path/'forecasts.json')
    monkeypatch.setattr(p, 'LOCK', asyncio.Lock())
    monkeypatch.setattr(macro, 'now', lambda: datetime.fromisoformat(STAMP.replace('Z','+00:00')))
    d=p.read(); d['scheduleDay']=p.schedule_day(macro.now())
    d['sources']=[{'id':x,'status':'ok'} for x in ['scotia','cleveland','rbc','usbank']]; p.write(d)
    calls=[]
    async def collect(name,*args): calls.append(name); return []
    monkeypatch.setattr(bank,'collect',collect)
    async def run():
        await p.update(); await p.update()
    asyncio.run(run())
    assert calls == ['rbc','usbank']


def row(source,value,kind='institution',stale=False,unit='%',ref='2026-10'):
    return {'id':source+str(value),'sourceId':source,'source':source,'kind':kind,'stale':stale,'metric':{'value':value,'unit':unit},'indicator':'cpi_mom','reference':ref,'sourceUpdatedAt':'2026-11-06','retrievedAt':STAMP}


def test_comparison_dedup_and_exclusion_of_model_consensus_stale():
    rows=[row('scotia',.3),row('scotia',.3),row('rbc',.3),row('usbank',.4),row('cleveland',.24,'model'),row('survey',.2,'consensus'),row('old',.9,stale=True)]
    result=p.compare_institutions(rows)
    assert result['count']==3 and result['median']['value']==.3
    assert result['spread']=={'value':.1,'unit':'百分点'}
    assert p.compare_institutions([row('rbc',.3)]) is None
    assert p.compare_institutions([row('rbc',.3),row('usbank',.4,ref='2026-09')]) is None
    assert p.compare_institutions([row('rbc',.3),row('usbank',.4,unit='人')]) is None


def test_payroll_difference_in_people():
    result=p.compare_institutions([row('scotia',100000,unit='人'),row('rbc',42000,unit='人')])
    assert result['spread']=={'value':58000,'unit':'人'} and result['median']['value']==71000


def test_new_sources_bootstrap_once_without_old_requests(monkeypatch,tmp_path):
    monkeypatch.setattr(p,'STORE',tmp_path/'forecasts.json')
    monkeypatch.setattr(p,'LOCK',asyncio.Lock())
    monkeypatch.setattr(macro,'now',lambda:datetime.fromisoformat(STAMP.replace('Z','+00:00')))
    d=p.read();d['scheduleDay']=p.schedule_day(macro.now());d['sources']=[{'id':x,'status':'ok'} for x in ['scotia','cleveland']];p.write(d)
    calls=[]
    async def collect(name,*args):calls.append(name);return []
    monkeypatch.setattr(bank,'collect',collect)
    async def unexpected(*args,**kwargs):raise AssertionError('Old sources should not refresh')
    monkeypatch.setattr(p,'fetch',unexpected)
    async def run():
        await p.update();await p.update()
    asyncio.run(run())
    assert calls==['rbc','usbank']
