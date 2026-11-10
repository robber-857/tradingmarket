from datetime import date

import pytest

from server.financials import Extractor, debt_from, fact, growth, missing, ratio


def record(value,start='2025-01-01',end='2025-06-30',filed='2025-08-01',accn='0000000001-25-000001',form='10-Q'):
    return dict(val=value,start=start,end=end,filed=filed,accn=accn,form=form)


def extractor(tags):
    return Extractor({'cik':1,'facts':{'us-gaap':tags}}, {'filings':{'recent':{
        'form':[],'accessionNumber':[],'primaryDocument':[],'reportDate':[],'filingDate':[]}}})


def concept(values,unit='USD'):
    return {'units':{unit:values}}


def test_ytd_cashflow_is_differenced_not_treated_as_a_quarter():
    x=extractor({'NetCashProvidedByUsedInOperatingActivities':concept([
        record(40,end='2025-03-31'),record(95)])})
    q=x.quarter('operating_cash_flow','2025-06-30')
    assert q['value']==55
    assert q['start']=='2025-04-01'
    assert q['status']=='derived'
    assert len(q['evidence'])==2


def test_q4_subtracts_nine_months_not_previous_quarter():
    x=extractor({'Revenues':concept([
        record(75,end='2025-09-30'),record(120,end='2025-12-31',form='10-K',filed='2026-02-01'),
        record(30,start='2025-07-01',end='2025-09-30')])})
    assert x.quarter('revenue','2025-12-31')['value']==45


def test_direct_quarter_wins_over_ytd():
    x=extractor({'Revenues':concept([record(120),record(50,start='2025-04-01')])})
    assert x.quarter('revenue','2025-06-30')['value']==50


def test_different_fiscal_starts_not_subtracted():
    x=extractor({'Revenues':concept([record(40,start='2024-12-29',end='2025-03-31'),record(95)])})
    assert x.quarter('revenue','2025-06-30')['value'] is None


def test_different_tags_not_mixed():
    x=extractor({'Revenues':concept([record(95)]),'SalesRevenueNet':concept([record(40,end='2025-03-31')])})
    assert x.quarter('revenue','2025-06-30')['value'] is None


@pytest.mark.parametrize('key,tag,unit',[('eps','EarningsPerShareDiluted','USD/shares'),
                                     ('diluted_shares','WeightedAverageNumberOfDilutedSharesOutstanding','shares')])
def test_nonadditive_metrics_never_differenced(key,tag,unit):
    x=extractor({tag:concept([record(1,end='2025-03-31'),record(3)],unit)})
    assert x.quarter(key,'2025-06-30')['value'] is None


def test_revised_and_future_records():
    x=extractor({'Revenues':concept([record(45,start='2025-04-01'),
        record(50,start='2025-04-01',filed='2025-09-01'),record(999,start='2025-04-01',filed='2099-01-01')])})
    q=x.quarter('revenue','2025-06-30')
    assert q['value']==50
    assert q['evidence'][0]['filed']=='2025-09-01'


@pytest.mark.parametrize('base',[0,-1,-100])
def test_loss_base_growth_is_not_percentage(base):
    assert growth(fact(100),fact(base))['value'] is None


def test_ratio_missing_never_zero_filled():
    assert ratio(fact(10),missing('absent'),'ratio')['value'] is None
    assert ratio(fact(10),fact(0),'ratio')['value'] is None
    assert growth(fact(120),fact(100))['value']==pytest.approx(.2)


def test_current_debt_not_double_counted():
    stock={k:fact(v) for k,v in {'debt_current':5,'debt_lt_current':4,'debt_lt_noncurrent':20,'commercial_paper':1,'short_borrowings':0}.items()}
    assert debt_from(stock)['value']==25
    stock['debt_current']=missing('not disclosed')
    assert debt_from(stock)['value']==25
    stock['debt_lt_noncurrent']=missing('not disclosed')
    assert debt_from(stock)['value'] is None


def test_only_10q_10k_facts_used():
    x=extractor({'Revenues':concept([record(50,start='2025-04-01'),record(999,start='2025-04-01',filed='2025-09-01',form='8-K')])})
    assert x.quarter('revenue','2025-06-30')['value']==50
