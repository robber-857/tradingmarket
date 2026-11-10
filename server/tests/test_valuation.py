import math

import pytest
from pydantic import ValidationError
from server.valuation import Assumptions, WaccInputs, calculate_wacc, dcf, valuation_bundle
from server.financials import fact


def params(**updates):
    return Assumptions(**{'growth':0,'target_margin':.2,'tax_rate':.25,'wacc':.1,
        'terminal_growth':0,'sales_to_capital':2,'terminal_roic':.12,'excess_cash':5,
        'debt':20,'shares':10,**updates})


def test_constant_cashflow_matches_perpetuity_closed_form():
    # EBIT=20, NOPAT=15, no net reinvestment; PV = 15 / .10 = 150.
    result=dcf(100,.2,params())
    assert result['enterpriseValue']==pytest.approx(150)
    assert result['valuePerShare']==pytest.approx(13.5)
    assert result['rows'][0]['fcff']==15
    assert result['equityResidual']==pytest.approx(135)


def test_wacc_capm_market_weights_hand_calculation():
    p=WaccInputs(risk_free=.04,beta=1,equity_risk_premium=.05,cost_of_debt=.05,
                 tax_rate=.25,equity_market_value=80,debt_market_value=20)
    out=calculate_wacc(p)
    assert out['costOfEquity']==pytest.approx(.09)
    assert out['wacc']==pytest.approx(.0795)


def test_terminal_growth_requires_reinvestment():
    r=dcf(100,.2,params(terminal_growth=.03,terminal_roic=.12))
    assert r['terminal']['reinvestment']==pytest.approx(r['terminal']['nopat']*.25)
    assert r['terminal']['fcff']==pytest.approx(r['terminal']['nopat']*.75)


def test_no_free_growth_when_terminal_roic_equals_cost_of_capital():
    a=dcf(100,.2,params(terminal_growth=.01,terminal_roic=.1))
    b=dcf(100,.2,params(terminal_growth=.03,terminal_roic=.1))
    # Next year's NOPAT itself grows; terminal value / (1+g) is invariant.
    assert a['terminal']['value']/1.01==pytest.approx(b['terminal']['value']/1.03)


@pytest.mark.parametrize('updates',[{'terminal_growth':.05,'wacc':.05}, {'terminal_growth':.03,'terminal_roic':.02},
 {'shares':0}, {'growth':float('nan')}, {'wacc':float('inf')}, {'tax_rate':-.1}, {'debt':-1}])
def test_invalid_inputs_rejected(updates):
    with pytest.raises(ValidationError):params(**updates)


def test_loss_year_no_invented_tax_refund():
    r=dcf(100,-.2,params(target_margin=.2))
    assert r['rows'][0]['ebit']<0
    assert r['rows'][0]['tax']==0


def test_higher_discount_rate_lowers_value_for_positive_cashflows():
    assert dcf(100,.2,params(wacc=.12))['valuePerShare'] < dcf(100,.2,params(wacc=.08))['valuePerShare']


def test_negative_residual_does_not_emit_negative_share_price():
    r=dcf(100,.2,params(debt=1000,comparison_price=10))
    assert r['equityResidual']<0
    assert r['valuePerShare'] is None
    assert r['marginOfSafety'] is None


def test_safety_margin_does_not_use_upside_formula():
    r=dcf(100,.2,params(comparison_price=10.8))
    assert r['marginOfSafety']==pytest.approx(.2)


def test_dcf_has_consistent_bridge_and_trace():
    r=dcf(100,.2,params(growth=.1,other_claims=3,nonoperating_assets=7))
    assert r['enterpriseValue']==pytest.approx(sum(x['presentValue'] for x in r['rows'])+r['terminal']['presentValue'])
    assert r['equityResidual']==pytest.approx(r['enterpriseValue']+5+7-20-3)
    assert r['rows'][0]['reinvestment']==pytest.approx(5)


def test_roic_and_sensitivity_invalid_cells():
    q={'end':'2025-12-31','ttm':{'revenue':fact(100),'operating_margin':fact(.2),'operating_income':fact(20)},'averageInvestedCapital':fact(80)}
    r=valuation_bundle(q,params(wacc=.04,terminal_growth=.035))
    assert r['roic']==pytest.approx(.1875)
    assert r['sensitivity']['values'][0][-1] is None
    assert len(r['base']['rows'])==5


def test_declining_revenue_no_automatic_asset_release():
    r=dcf(100,.2,params(growth=-.1))
    assert all(row['reinvestment']==0 for row in r['rows'])
