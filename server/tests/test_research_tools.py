from datetime import date,timedelta
import pytest
from server.financials import fact
from server.valuation import Assumptions,BetaInputs,calculate_beta,relative_valuation


def beta_sample():
    prices=[{'date':'2025-01-01','asset':100,'benchmark':100}]
    for i in range(1,25):
        r=((i%5)-2)*.01
        prices.append({'date':(date(2025,1,1)+timedelta(days=7*i)).isoformat(),
                       'asset':prices[-1]['asset']*(1+.002+2*r),
                       'benchmark':prices[-1]['benchmark']*(1+r)})
    return {'benchmark':'SPY','frequency':'weekly','prices':prices}


def test_beta_recovers_known_regression():
    result=calculate_beta(BetaInputs(**beta_sample()))
    assert result['beta']==pytest.approx(2)
    assert result['alphaPerPeriod']==pytest.approx(.002)
    assert result['rSquared']==pytest.approx(1)
    assert result['observations']==24


def test_beta_rejects_unaligned_dates_and_zero_variance():
    sample=beta_sample();sample['prices'][1]['date']=sample['prices'][0]['date']
    with pytest.raises(ValueError):calculate_beta(BetaInputs(**sample))
    sample=beta_sample()
    for row in sample['prices']:row['benchmark']=100
    with pytest.raises(ValueError):calculate_beta(BetaInputs(**sample))


def test_beta_requires_enough_positive_prices():
    sample=beta_sample();sample['prices']=sample['prices'][:5]
    with pytest.raises(ValueError):BetaInputs(**sample)
    sample=beta_sample();sample['prices'][3]['asset']=0
    with pytest.raises(ValueError):BetaInputs(**sample)


def test_relative_values_use_same_price_and_shares():
    q={'ttm':{'net_income':fact(20),'revenue':fact(100)},'stock':{'equity':fact(50)}}
    p=Assumptions(debt=0,shares=10,comparison_price=20)
    result=relative_valuation(q,p)
    assert result['marketCap']==200
    assert [result['metrics'][x]['value'] for x in ('pe','pb','ps')]==[10,4,2]


@pytest.mark.parametrize('net,equity',[(0,0),(-10,-20),(None,None)])
def test_relative_values_do_not_invent_profit_or_book_value(net,equity):
    q={'ttm':{'net_income':fact(net),'revenue':fact(100)},'stock':{'equity':fact(equity)}}
    result=relative_valuation(q,Assumptions(debt=0,shares=10,comparison_price=20))
    assert result['metrics']['pe']['value'] is None
    assert result['metrics']['pb']['value'] is None
    assert result['metrics']['ps']['value']==2


def test_relative_values_require_manual_price():
    q={'ttm':{'net_income':fact(20),'revenue':fact(100)},'stock':{'equity':fact(50)}}
    result=relative_valuation(q,Assumptions(debt=0,shares=10))
    assert all(v['value'] is None for v in result['metrics'].values())
