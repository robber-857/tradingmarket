"""Auditable five-year FCFF valuation. Inputs are explicit user assumptions."""
from math import isfinite
from datetime import date
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = 'fcff-sales-capital-1.0.0'


class Assumptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    growth: float = Field(default=.08, ge=-.3, le=.6)
    target_margin: float = Field(default=.2, gt=0, le=.8)
    tax_rate: float = Field(default=.25, ge=0, le=.5)
    wacc: float = Field(default=.10, ge=.02, le=.4)
    terminal_growth: float = Field(default=.025, ge=0, le=.05)
    sales_to_capital: float = Field(default=2, ge=.25, le=10)
    terminal_roic: float = Field(default=.12, ge=.01, le=.5)
    excess_cash: float = Field(default=0, ge=0, le=1e13)
    nonoperating_assets: float = Field(default=0, ge=0, le=1e13)
    debt: float = Field(ge=0, le=1e13)
    other_claims: float = Field(default=0, ge=0, le=1e13)
    shares: float = Field(gt=0, le=1e13)
    comparison_price: float | None = Field(default=None, gt=0, le=1e7)

    @model_validator(mode='after')
    def valid_terminal(self):
        if self.wacc <= self.terminal_growth:
            raise ValueError('WACC 必须大于永续增长率，否则终值不成立。')
        if self.terminal_roic <= self.terminal_growth:
            raise ValueError('稳定期 ROIC 必须大于永续增长率，才能维持正的终值现金流。')
        return self


class WaccInputs(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    risk_free: float = Field(ge=0, le=.2)
    beta: float = Field(ge=0, le=5)
    equity_risk_premium: float = Field(ge=0, le=.2)
    cost_of_debt: float = Field(ge=0, le=.4)
    tax_rate: float = Field(ge=0, le=.5)
    equity_market_value: float = Field(gt=0, le=1e15)
    debt_market_value: float = Field(ge=0, le=1e15)


class PricePair(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    date: date
    asset: float = Field(gt=0, le=1e10)
    benchmark: float = Field(gt=0, le=1e10)


class BetaInputs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    benchmark: str = Field(min_length=1, max_length=30)
    frequency: str = Field(pattern=r'^(daily|weekly|monthly)$')
    prices: list[PricePair] = Field(min_length=21, max_length=1500)


def calculate_beta(p: BetaInputs):
    dates=[r.date for r in p.prices]
    if dates!=sorted(set(dates)):
        raise ValueError('样本日期必须严格递增且不重复，请先对齐资产和基准价格。')
    market=[b.benchmark/a.benchmark-1 for a,b in zip(p.prices,p.prices[1:])]
    asset=[b.asset/a.asset-1 for a,b in zip(p.prices,p.prices[1:])]
    mx,my=mean(market),mean(asset)
    xx=sum((x-mx)**2 for x in market)
    yy=sum((y-my)**2 for y in asset)
    xy=sum((x-mx)*(y-my) for x,y in zip(market,asset))
    if xx<=1e-15: raise ValueError('基准收益率没有足够波动，无法估计 Beta。')
    beta=xy/xx
    return {'beta':beta,'alphaPerPeriod':my-beta*mx,'rSquared':xy*xy/(xx*yy) if yy>1e-15 else None,
            'observations':len(market),'start':dates[0].isoformat(),'end':dates[-1].isoformat(),
            'benchmark':p.benchmark,'frequency':p.frequency,
            'formula':'β = Cov(资产简单收益率, 基准简单收益率) / Var(基准简单收益率)',
            'basis':'用户导入、按日期配对的复权价格；未独立验证来源或频率。历史 OLS Beta，不是未来风险预测。',
            'modelVersion':'beta-ols-1.0.0'}


def relative_valuation(quarter, p: Assumptions):
    price=p.comparison_price
    cap=price*p.shares if price is not None else None
    net=quarter['ttm'].get('net_income',{}).get('value')
    equity=quarter.get('stock',{}).get('equity',{}).get('value')
    revenue=quarter['ttm']['revenue']['value']
    items={}
    for name,denominator,formula in [('pe',net,'手动价格 × 估值股数 / TTM 归属净利润'),
                                    ('pb',equity,'手动价格 × 估值股数 / 期末母公司账面权益'),
                                    ('ps',revenue,'手动价格 × 估值股数 / TTM 营收')]:
        reason=('未输入对比价格' if cap is None else '所需财报输入缺失' if denominator is None
                else '分母非正，倍数不适用' if denominator<=0 else None)
        source=quarter.get('stock',{}).get('equity',{}) if name=='pb' else quarter['ttm'].get('net_income' if name=='pe' else 'revenue',{})
        items[name]={'value':None if reason else cap/denominator,'formula':formula,'reason':reason,
                     'numerator':cap,'denominator':denominator,'evidence':source.get('evidence',[]),
                     'warning':'分子使用用户输入价格与估值股数，非实时官方市值。'}
    return {'marketCap':cap,'price':price,'shares':p.shares,'metrics':items,
            'basis':'手动价格与估值股数构造的市值，结合所选报告期 TTM 或期末数据；非实时市场倍数。未提供同业中位数或历史分位，不能仅凭倍数判断低估。'}


def calculate_wacc(p: WaccInputs):
    ke = p.risk_free + p.beta * p.equity_risk_premium
    total = p.equity_market_value+p.debt_market_value
    ew = p.equity_market_value/total
    wacc = ew*ke+(1-ew)*p.cost_of_debt*(1-p.tax_rate)
    return {'costOfEquity':ke,'equityWeight':ew,'debtWeight':1-ew,'wacc':wacc,
            'formula':'Ke = Rf + β × ERP；WACC = E/(D+E) × Ke + D/(D+E) × Kd × (1−T)',
            'basis':'用户输入的市场价值权重；并非自动获取的市场资本成本', 'modelVersion':VERSION}


def dcf(revenue: float, margin: float, p: Assumptions):
    if not isfinite(revenue) or revenue<=0 or not isfinite(margin):
        raise ValueError('DCF 需要正值 TTM 营收和有效的营业利润率。')
    rows=[]
    current=revenue
    for year in range(1,6):
        previous=current
        current=previous*(1+p.growth)
        operating_margin=margin+(p.target_margin-margin)*year/5
        ebit=current*operating_margin
        # Losses incur no modeled current tax benefit; no hidden NOL assumption.
        taxes=max(ebit,0)*p.tax_rate
        nopat=ebit-taxes
        reinvestment=max(current-previous,0)/p.sales_to_capital
        fcff=nopat-reinvestment
        discount=(1+p.wacc)**year
        rows.append({'year':year,'revenue':current,'margin':operating_margin,'ebit':ebit,
                     'tax':taxes,'nopat':nopat,'reinvestment':reinvestment,'fcff':fcff,
                     'discountFactor':discount,'presentValue':fcff/discount})
    terminal_nopat=rows[-1]['nopat']*(1+p.terminal_growth)
    terminal_reinvestment=terminal_nopat*p.terminal_growth/p.terminal_roic
    terminal_fcff=terminal_nopat-terminal_reinvestment
    terminal_value=terminal_fcff/(p.wacc-p.terminal_growth)
    terminal_pv=terminal_value/(1+p.wacc)**5
    explicit_pv=sum(r['presentValue'] for r in rows)
    ev=explicit_pv+terminal_pv
    residual=ev+p.excess_cash+p.nonoperating_assets-p.debt-p.other_claims
    # Negative residuals aren't a negative tradable share price or a useful price target.
    per_share=residual/p.shares if residual>0 else None
    safety=1-p.comparison_price/per_share if p.comparison_price and per_share else None
    warnings=[]
    if ev<=0 or residual<=0:
        warnings.append('剩余股权价值非正：简单持续经营 DCF 不适合给出有效每股估值，需重组/情景研究。')
    terminal_weight=terminal_pv/ev if ev>0 else None
    if terminal_weight is not None and terminal_weight>.7:
        warnings.append('终值现值占企业价值超过 70%；这是产品提示阈值，结果高度依赖远期假设。')
    if p.wacc-p.terminal_growth<.02:
        warnings.append('WACC 与永续增长率差距不足 2 个百分点，终值对微小变化敏感。')
    if p.growth<0:
        warnings.append('收入下降情景不假设资本自动释放，净再投资下限设为零。')
    if margin<0:
        warnings.append('起点营业亏损，模型依赖五年内达到目标利润率；没有自动预测扭亏。')
    return {'rows':rows,'enterpriseValue':ev,'explicitPresentValue':explicit_pv,
            'terminal':{'nopat':terminal_nopat,'reinvestment':terminal_reinvestment,
                        'fcff':terminal_fcff,'value':terminal_value,'presentValue':terminal_pv,'weight':terminal_weight},
            'equityResidual':residual,'valuePerShare':per_share,'marginOfSafety':safety,
            'warnings':warnings,'assumptions':p.model_dump(),'modelVersion':VERSION}


def valuation_bundle(quarter, p: Assumptions):
    revenue=quarter['ttm']['revenue']['value']; margin=quarter['ttm']['operating_margin']['value']
    if revenue is None or margin is None:
        raise ValueError('缺少完整 TTM 收入或营业利润，暂不生成 DCF。')
    base=dcf(revenue,margin,p)
    scenarios=[]
    # Named stress cases, not probabilities or an assertion of value ordering.
    for name,dg,dm,dw in [('悲观',-.05,-.03,.01),('基准',0,0,0),('乐观',.05,.03,-.01)]:
        a=p.model_dump()
        a.update(growth=max(-.3,min(.6,p.growth+dg)),target_margin=max(.005,min(.8,p.target_margin+dm)),
                 wacc=max(.02,min(.4,p.wacc+dw)))
        try:
            scenario=dcf(revenue,margin,Assumptions(**a))
            scenarios.append({'name':name,**scenario})
        except ValueError:
            scenarios.append({'name':name,'valuePerShare':None,'error':'该情景不满足终值约束'})
    sensitivity=[]
    rates=[p.wacc+v for v in (-.02,-.01,0,.01,.02)]
    growths=[p.terminal_growth+v for v in (-.01,-.005,0,.005,.01)]
    for rate in rates:
        row=[]
        for g in growths:
            try:
                a=Assumptions(**{**p.model_dump(),'wacc':rate,'terminal_growth':g})
                row.append(dcf(revenue,margin,a)['valuePerShare'])
            except ValueError:
                row.append(None)
        sensitivity.append(row)
    ic=quarter['averageInvestedCapital']['value']
    op=quarter['ttm']['operating_income']['value']
    roic=op*(1-p.tax_rate)/ic if ic and ic>0 and op is not None and op>=0 else None
    return {'base':base,'scenarios':scenarios,'sensitivity':{'wacc':rates,'growth':growths,'values':sensitivity},
            'multiples':relative_valuation(quarter,p),
            'roic':roic,'roicSpread':roic-p.wacc if roic is not None else None,
            'roicBasis':'简化 ROIC：TTM 营业利润 × (1−假设税率) / 两期平均账面投入资本；未调整研发资本化、租赁和商誉。亏损期不计算税盾。',
            'baseline':{'revenue':revenue,'operatingMargin':margin,'reportEnd':quarter['end']},
            'assumptionNotice':'增长、目标利润率、WACC、税率、稳定期 ROIC 与再投资效率均为可修改假设，不是公司指引或市场一致预期。'}
