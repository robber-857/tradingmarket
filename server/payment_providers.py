"""Test-only payment transports. Live credentials/endpoints are deliberately rejected."""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from . import membership as m

STRIPE_VERSION = '2024-06-20'
PAYPAL_BASE = 'https://api-m.sandbox.paypal.com'


def enabled():
    return m.config('BILLING_TEST_ENABLED', '0') == '1'


def availability():
    stripe_key=m.config('STRIPE_TEST_SECRET_KEY')
    return {'testMode':True, 'enabled':enabled(),
            'stripe':enabled() and stripe_key.startswith('sk_test_') and bool(m.config('STRIPE_TEST_WEBHOOK_SECRET')),
            'paypal':enabled() and bool(m.config('PAYPAL_SANDBOX_CLIENT_ID')) and bool(m.config('PAYPAL_SANDBOX_CLIENT_SECRET')) and bool(m.config('PAYPAL_SANDBOX_WEBHOOK_ID'))}


def require(provider):
    if not availability().get(provider):
        raise HTTPException(503, '该测试支付渠道尚未配置，请查看收款配置说明。')


def provider_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',value):
        raise HTTPException(400,'支付渠道编号无效。')
    return value


async def stripe(method, path, data=None, key=None):
    require('stripe')
    headers={'Authorization':'Bearer '+m.config('STRIPE_TEST_SECRET_KEY'), 'Stripe-Version':STRIPE_VERSION}
    if key:headers['Idempotency-Key']=key
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.request(method,'https://api.stripe.com/v1/'+path,headers=headers,data=data)
        if response.status_code>=400:
            raise HTTPException(502,'Stripe 测试请求未完成，请稍后重试；不要重复创建付款。')
        result=response.json()
        if result.get('livemode') is True:
            raise HTTPException(409,'测试环境拒绝正式付款对象。')
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502,'测试支付连接异常，请稍后重试同一订单。') from exc


async def paypal(method,path,data=None,key=None):
    require('paypal')
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token=await client.post(PAYPAL_BASE+'/v1/oauth2/token',
                auth=(m.config('PAYPAL_SANDBOX_CLIENT_ID'),m.config('PAYPAL_SANDBOX_CLIENT_SECRET')),
                data={'grant_type':'client_credentials'})
            if token.status_code>=400:raise HTTPException(503,'PayPal Sandbox 账户配置不可用。')
            headers={'Authorization':'Bearer '+token.json()['access_token'],'Content-Type':'application/json'}
            if key:headers['PayPal-Request-Id']=key
            response=await client.request(method,PAYPAL_BASE+path,headers=headers,json=data)
        if response.status_code>=400:
            raise HTTPException(502,'PayPal 测试请求未完成，请重试同一订单。')
        return response.json() if response.content else {}
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        raise HTTPException(502,'PayPal 测试连接异常，请稍后重试。') from exc


def verify_stripe(raw, signature):
    require('stripe')
    try:
        fields=[part.split('=',1) for part in signature.split(',')]
        stamp=next(v for k,v in fields if k=='t')
        if abs(time.time()-int(stamp))>300:raise ValueError()
        expected=hmac.new(m.config('STRIPE_TEST_WEBHOOK_SECRET').encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if not any(k=='v1' and hmac.compare_digest(v,expected) for k,v in fields):raise ValueError()
        event=json.loads(raw)
        if event.get('livemode') is not False:raise ValueError()
        provider_id(event['id'])
        return event
    except (ValueError,KeyError,StopIteration,TypeError) as exc:
        raise HTTPException(400,'支付回调签名或测试环境校验失败。') from exc


async def verify_paypal(raw,headers):
    try:
        event=json.loads(raw)
        payload={'auth_algo':headers['paypal-auth-algo'],'cert_url':headers['paypal-cert-url'],
                 'transmission_id':headers['paypal-transmission-id'],'transmission_sig':headers['paypal-transmission-sig'],
                 'transmission_time':headers['paypal-transmission-time'],
                 'webhook_id':m.config('PAYPAL_SANDBOX_WEBHOOK_ID'),'webhook_event':event}
        # Never fetch the supplied certificate URL ourselves.
        result=await paypal('POST','/v1/notifications/verify-webhook-signature',payload)
        if result.get('verification_status')!='SUCCESS':raise ValueError()
        provider_id(event['id'])
        return event
    except (ValueError,KeyError,TypeError) as exc:
        raise HTTPException(400,'PayPal 测试回调签名校验失败。') from exc


def checkout_url(url,provider):
    parsed=urlparse(url or '')
    hosts={'stripe':{'checkout.stripe.com'},'paypal':{'www.sandbox.paypal.com','sandbox.paypal.com'}}
    if parsed.scheme!='https' or parsed.hostname not in hosts[provider]:
        raise HTTPException(502,'支付渠道未返回有效测试结账地址。')
    return url
