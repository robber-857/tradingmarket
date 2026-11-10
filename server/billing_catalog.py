"""Server-owned checkout quotations; providers cannot accept browser prices.

No charge is created by the quote endpoint; billing.py handles test checkout.
"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from . import membership as m

router = APIRouter(prefix='/api/billing')


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan: Literal['research', 'advanced', 'expert']
    currency: Literal['cny', 'aud', 'usd']
    period: Literal['week', 'month'] = 'month'
    method: Literal['alipay', 'card', 'apple_pay', 'paypal']


def quote(body):
    if body.currency == 'cny' and body.method != 'alipay':
        raise HTTPException(422, '人民币方案使用支付宝单次购买。')
    if body.currency != 'cny' and body.method == 'alipay':
        raise HTTPException(422, '请选择人民币支付宝方案，或使用银行卡／Apple Pay。')
    if body.period == 'week' and body.plan != 'research':
        raise HTTPException(422, '七天通行证仅提供研究会员权益。')
    offer = m.WEEK if body.period == 'week' else m.PLANS[body.plan]
    return {'plan': body.plan, 'currency': body.currency, 'amountMinor': offer['prices'][body.currency],
            'period': body.period, 'method': body.method,
            'renewal': 'manual' if body.period == 'week' or body.method in ('alipay','paypal') else 'automatic',
            'limits': offer['limits'], 'salesEnabled': False,
            'taxStatus': '待商户税务配置，当前不是可付款账单',
            'provider': 'paypal' if body.method == 'paypal' else 'stripe'}


@router.post('/quote')
def get_quote(body: QuoteRequest, request: Request):
    m.current_user(request, True)
    return quote(body)
