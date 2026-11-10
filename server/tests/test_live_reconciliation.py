"""Read-only reconciliation against locally downloaded SEC payloads.

These checks skip in a clean checkout; they never contact the network or make
up a filing. The regular unit suite remains fully offline and reproducible.
"""
import json
from pathlib import Path

import pytest

from server.financials import Extractor, FLOW_TAGS, build_report
from server.sec import CACHE, COMPANIES


@pytest.fixture(params=list(COMPANIES))
def official(request):
    symbol=request.param
    files=[CACHE/f'{symbol}-{k}.json' for k in ('facts','submissions')]
    if not all(p.exists() for p in files):
        pytest.skip('No local official SEC cache; no network in tests')
    facts,submissions=[json.loads(p.read_text(encoding='utf-8-sig')) for p in files]
    return symbol,Extractor(facts,submissions),build_report(symbol,COMPANIES[symbol],facts,submissions,[])


def test_independent_annual_totals_reconcile_with_four_quarters(official):
    symbol,x,report=official
    annual=max((f for f in x.filings if f['form']=='10-K'),key=lambda f:f['end'])
    annual_end=annual['end']
    quarters=[q for q in report['quarters'] if q['end']<=annual_end][:4]
    assert len(quarters)==4
    for key in ['revenue','operating_cash_flow','capex']:
        annual_fact=x.direct(FLOW_TAGS[key],annual_end,(330,380))
        if annual_fact['value'] is None:
            continue
        total=sum(q['flow'][key]['value'] for q in quarters)
        # Integer dollar disclosures sum exactly (minor rounding tolerance).
        assert total==pytest.approx(annual_fact['value'],abs=1), (symbol,key)


def test_balance_and_source_metadata_are_consistent(official):
    symbol,x,report=official
    q=report['quarters'][0]
    s=q['stock']
    assert s['assets']['value']==pytest.approx(s['liabilities']['value']+s['total_equity']['value'],abs=1e6)
    assert q['ttm']['revenue']['value'] is not None
    for field in q['flow'].values():
        if field['value'] is not None:
            assert field['evidence']
            for evidence in field['evidence']:
                assert evidence['form'] in ('10-Q','10-K','10-Q/A','10-K/A')
                assert evidence['url'].startswith('https://www.sec.gov/Archives/edgar/data/')
                assert evidence['tag'].startswith('us-gaap:')
    assert report['basis']=='latest_restated'
