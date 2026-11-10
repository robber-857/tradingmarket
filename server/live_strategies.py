"""Compose only server-owned contracts. Quotes and Greeks never come from the client."""
from datetime import date, datetime, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import options, option_strategies as payoff, news

VERSION = 'live-strategies-1.0'
TEMPLATES = [
    ('long-call','买入看涨',0,[('call',1,0)]),
    ('long-put','买入看跌',0,[('put',1,0)]),
    ('covered-call','备兑看涨',100,[('call',-1,1)]),
    ('protective-put','保护性看跌',100,[('put',1,-1)]),
    ('bull-call','牛市看涨价差',0,[('call',1,0),('call',-1,1)]),
    ('bear-put','熊市看跌价差',0,[('put',1,0),('put',-1,-1)]),
    ('bull-put','牛市看跌信用价差',0,[('put',-1,0),('put',1,-1)]),
    ('bear-call','熊市看涨信用价差',0,[('call',-1,0),('call',1,1)]),
    ('long-straddle','买入跨式',0,[('call',1,0),('put',1,0)]),
    ('iron-condor','铁鹰',0,[('put',1,-2),('put',-1,-1),('call',-1,1),('call',1,2)]),
    ('collar','领口策略',100,[('put',1,-1),('call',-1,1)])]


class LiveLeg(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contract_id: str = Field(min_length=1,max_length=100)
    quantity: int = Field(ge=-10,le=10,strict=True)

    @model_validator(mode='after')
    def nonzero(self):
        if not self.quantity: raise ValueError('合约份数不能为零')
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=40)
    stock_shares: Literal[0,100] = 0
    legs: list[LiveLeg] = Field(min_length=1,max_length=4)

    @model_validator(mode='after')
    def unique(self):
        if len({l.contract_id for l in self.legs})!=len(self.legs): raise ValueError('同一组合不能重复选择同一合约')
        return self


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chain_snapshot_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    price_basis: Literal['natural','mid'] = 'natural'
    fee_per_contract: float = Field(default=0,ge=0,le=50,allow_inf_nan=False)
    scenarios: list[Scenario] = Field(min_length=1,max_length=4)

    @model_validator(mode='after')
    def unique(self):
        if len({s.name for s in self.scenarios})!=len(self.scenarios):raise ValueError('比较组合名称必须不同')
        return self


def chain_snapshot(ident):
    chain=options.load_snapshot(ident)
    if 'contracts' not in chain or chain.get('mode'): raise news.NewsError(422,'请选择真实期权链快照')
    if (news.now()-news.date_time(chain['calculatedAt'])).total_seconds()>900 or (news.now()-news.date_time(chain['retrievedAt'])).total_seconds()>1800:
        raise news.NewsError(409,'期权链快照已过期，请重新读取链并确认合约报价')
    if datetime.combine(date.fromisoformat(chain['expiry']),time(16),options.ET)<=news.now():
        raise news.NewsError(409,'所选期权已到期，请选择新的到期日')
    return chain


def premium(row,basis,quantity):
    bid,ask=row['bid'],row['ask']
    if bid is None or ask is None or not 0<=bid<=ask or ask<=0:
        raise news.NewsError(422,'所选合约缺少有效双边报价；不会使用 Last 或假定零价格替代')
    if basis=='mid':
        if row['mid'] is None:raise news.NewsError(422,'所选合约无有效中间价，请重新选择')
        return row['mid']
    return ask if quantity>0 else bid


def templates(ident):
    chain=chain_snapshot(ident);rows=chain['contracts'];spot=chain['spot']
    # Template strikes are structural starting points, not recommendations or liquidity optimisation.
    strikes=sorted({r['strike'] for r in rows})
    center=min(range(len(strikes)),key=lambda i:abs(strikes[i]-spot))
    lookup={(r['side'],r['strike']):r for r in rows};out=[]
    for key,name,shares,legs in TEMPLATES:
        selected=[]
        for side,qty,offset in legs:
            idx=center+offset
            if not 0<=idx<len(strikes) or (side,strikes[idx]) not in lookup:break
            selected.append({'contract_id':lookup[side,strikes[idx]]['id'],'quantity':qty})
        out.append({'id':key,'name':name,'stock_shares':shares,'legs':selected if len(selected)==len(legs) else [],
                    'available':len(selected)==len(legs),'notice':'以最接近标的的行权价及相邻档位搭建；请自行确认价格与风险'})
    return {'templates':out,'chainSnapshotId':ident}


def compare(req):
    chain=chain_snapshot(req.chain_snapshot_id);lookup={r['id']:r for r in chain['contracts']};results=[]
    for spec in req.scenarios:
        legs=[];missing=[];risk=[]
        for choice in spec.legs:
            row=lookup.get(choice.contract_id)
            if not row or row['expiry']!=chain['expiry']:raise news.NewsError(422,'合约不属于当前股票和到期日快照')
            px=premium(row,req.price_basis,choice.quantity)
            legs.append({**row,'quantity':choice.quantity,'entryPrice':px,'entrySide':('ask' if choice.quantity>0 else 'bid') if req.price_basis=='natural' else 'mid'})
            if row['greeks'] is None:missing.append(row['id'])
            if row['spreadPct'] is None or row['spreadPct']>30:risk.append('所选腿有宽价差或低质量报价，成交成本与模型可靠性受限')
            if row['bid']==0:risk.append('存在零买价合约，卖出收入按零计算，不保证能成交')
            if choice.quantity<0:risk.append('空头腿存在提前指派、保证金与临到期执行风险')
            if row['oi'] is None or row['oi']==0:risk.append('部分腿缺少持仓量或持仓量为零，流动性需核实')
        fees=req.fee_per_contract*sum(abs(l['quantity']) for l in legs)
        calc=payoff.calculate(payoff.StrategyRequest(name=spec.name,spot=chain['spot'],stock_shares=spec.stock_shares,
                         legs=[payoff.Leg(side=l['side'],quantity=l['quantity'],strike=l['strike'],premium=l['entryPrice']) for l in legs]),persist=False,fees=fees)
        greeks={k:None if missing else (spec.stock_shares if k=='delta' else 0)+100*sum(l['quantity']*l['greeks'][k] for l in legs)
                for k in ('delta','gamma','theta','vega','rho')}
        if missing:risk.append('有合约缺少可靠 IV/Greeks，组合 Greeks 不显示部分和')
        if calc['maxLoss'] is None:risk.append('当前组合理论最大损失无上限')
        if calc['bestPnl'] is not None and calc['bestPnl']<0:risk.append('当前报价与费用下，即使最优到期价格也无法覆盖建仓成本')
        if spec.stock_shares:risk.append('持股成本使用来源标的价格作新建仓假设，不代表你的历史成本或可成交股票报价')
        risk.append('期权为公开延迟报价，缺少逐合约时间；中间价和自然买卖价都不保证成交')
        if req.price_basis=='mid':risk.append('中间价是参考情景，可能低估实际多腿成交成本')
        result={k:calc[k] for k in ('name','maxProfit','maxLoss','bestPnl','worstPnl','breakEvens','netDebit','points')}
        result.update({'legs':legs,'stockShares':spec.stock_shares,'stockCost':chain['spot'] if spec.stock_shares else None,
                       'optionDebit':100*sum(l['quantity']*l['entryPrice'] for l in legs),'fees':fees,'greeks':greeks,
                       'greekCoverage':{'complete':not missing,'missingContracts':missing,'pricedLegs':len(legs)-len(missing),'totalLegs':len(legs)},
                       'spreadCost':100*sum(abs(l['quantity'])*(l['ask']-l['bid']) for l in legs),
                       'riskNotes':list(dict.fromkeys(risk))})
        results.append(result)
    result={'mode':'live_strategy_comparison','symbol':chain['symbol'],'expiry':chain['expiry'],'spot':chain['spot'],
            'chainSnapshotId':req.chain_snapshot_id,'sourceUrl':chain['sourceUrl'],'sourceAsOf':chain['sourceAsOf'],
            'retrievedAt':chain['retrievedAt'],'chainCalculatedAt':chain['calculatedAt'],'chainAsOf':chain['chainAsOf'],
            'assumptions':chain['assumptions'],'priceBasis':req.price_basis,'feePerContract':req.fee_per_contract,
            'strategies':results,'calculatedAt':news.iso(news.now()),'engineVersion':VERSION,
            'notice':'真实延迟报价上的建仓情景计算，非成交记录。全组合 Greeks 使用同一链快照 BSM 模型：Delta 含持股，其他按方向×份数×100 加总；Theta 每天，Vega/Rho 每百分点。到期盈亏含输入的开仓期权费用，不含融资、股息、平仓费与指派成本；净支出不等于保证金。'}
    result['snapshotId']=news.digest(result)
    news.atomic_json(options.SNAPSHOTS/(result['snapshotId']+'.json'),result)
    return result
