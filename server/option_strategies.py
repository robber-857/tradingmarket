"""Piecewise-linear expiry payoffs; no model-generated arithmetic."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import news, options


class Leg(BaseModel):
    model_config = ConfigDict(extra='forbid')
    side: Literal['call','put']
    quantity: int = Field(ge=-10,le=10)
    strike: float = Field(gt=0,le=100000,allow_inf_nan=False)
    premium: float = Field(ge=0,le=100000,allow_inf_nan=False)


class StrategyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=60)
    spot: float = Field(gt=0,le=100000,allow_inf_nan=False)
    stock_shares: Literal[0,100] = 0
    legs: list[Leg] = Field(min_length=1,max_length=4)


def calculate(req, *, persist=True, fees=0):
    def payoff(s):
        return req.stock_shares*(s-req.spot)+100*sum(l.quantity*(max(s-l.strike,0) if l.side=='call' else max(l.strike-s,0))-l.quantity*l.premium for l in req.legs)-fees
    knots = sorted({0.0,*[l.strike for l in req.legs]})
    values = [payoff(k) for k in knots]
    slope = req.stock_shares+100*sum(l.quantity for l in req.legs if l.side=='call')
    roots = []
    for a,b in zip(knots,knots[1:]):
        ya,yb = payoff(a),payoff(b)
        if abs(ya)<1e-8: roots.append(a)
        if ya*yb<0: roots.append(a-ya*(b-a)/(yb-ya))
    if abs(values[-1])<1e-8: roots.append(knots[-1])
    if slope and (root:=knots[-1]-values[-1]/slope)>knots[-1]: roots.append(root)
    high = max(req.spot*1.6,knots[-1]*1.2,*[r*1.15 for r in roots])
    points = sorted({*[high*i/100 for i in range(101)],*knots,*roots,req.spot})
    result = {'mode':'strategy','name':req.name,'inputs':req.model_dump(),
              'bestPnl':None if slope>0 else max(values),'worstPnl':None if slope<0 else min(values),
              'maxProfit':None if slope>0 else max(0,max(values)), 'maxLoss':None if slope<0 else max(0,-min(values)),
              'breakEvens':sorted(set(round(r,6) for r in roots)),
              'netDebit':req.stock_shares*req.spot+100*sum(l.quantity*l.premium for l in req.legs)+fees,
              'points':[{'price':s,'pnl':payoff(s)} for s in points],
              'sourceUrl':'https://www.optionseducation.org/strategies/all-strategies',
              'notice':'教学假设；统一到期、每份一百股，未计佣金、滑点、股息、融资和提前指派。到期前盈亏不同。空头腿仍有指派及保证金风险。',
              'calculatedAt':news.iso(news.now()), 'engineVersion':'strategy-payoff-1.0'}
    result['snapshotId'] = news.digest(result)
    if persist: news.atomic_json(options.SNAPSHOTS/(result['snapshotId']+'.json'),result)
    return result
