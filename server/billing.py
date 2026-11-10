"""Test-mode payment lifecycle. Browser returns never directly grant membership."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import secrets
import time
from typing import Literal
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from . import membership as m, payment_providers as p, billing_engine as e
from .billing_catalog import QuoteRequest, quote
from .member_api import origin

router=APIRouter(prefix='/api/billing')


class Checkout(QuoteRequest):
    request_key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


class RefundRequest(BaseModel):
    reason:str=Field(min_length=3,max_length=1000)


class ReviewRequest(BaseModel):
    approve:bool
    note:str=Field(min_length=3,max_length=1000)


def admin(request):
    user=m.current_user(request,True)
    ids={x.strip() for x in m.config('BILLING_ADMIN_USER_IDS').split(',') if x.strip()}
    if user['id'] not in ids:raise HTTPException(403,'需要退款管理员权限。')
    if not p.enabled():raise HTTPException(503,'测试支付未启用。')
    return user


def iso_epoch(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def minor(value):
    amount=Decimal(value)*100
    if not amount.is_finite() or amount!=amount.to_integral_value():raise HTTPException(409,'付款金额精度无效。')
    return int(amount)


@router.get('/status')
def status():
    return p.availability()


@router.get('/account')
def account(request:Request,response:Response):
    user=m.current_user(request,True)
    response.headers['Cache-Control']='no-store'
    return {**e.list_account(user['id']),'isAdmin':user['id'] in m.config('BILLING_ADMIN_USER_IDS').split(',')}


@router.post('/checkout')
async def checkout(body:Checkout,request:Request):
    user=m.current_user(request,True)
    offer=quote(body)
    # PayPal Sandbox Orders are single payments; monthly renewal is explicit.
    if body.method=='paypal':offer['renewal']='manual'
    p.require(offer['provider'])
    m.throttle('checkout:'+user['id'],10,60)
    order=e.new_order(user['id'],offer,body.request_key)
    if order['status'] not in ('creating','pending'):
        raise HTTPException(409,'此订单已处理，请刷新付款记录。')
    if order['status']=='creating' and time.time()-order['created']>23*3600:
        raise HTTPException(409,'创建结果不明的旧订单需先人工核对，不能重新发起扣款。')
    if order['checkout_url']:
        return {'orderId':order['id'],'url':order['checkout_url'],'testMode':True}
    return_url=origin()+'/?billing_order='+order['id']+'#membership'
    if offer['provider']=='stripe':
        subscription=offer['renewal']=='automatic'
        data={'mode':'subscription' if subscription else 'payment','success_url':return_url,'cancel_url':return_url,
              'client_reference_id':order['id'],'metadata[order_id]':order['id'],
              'customer_email':user['email'],'line_items[0][quantity]':'1',
              'line_items[0][price_data][currency]':body.currency,
              'line_items[0][price_data][unit_amount]':str(offer['amountMinor']),
              'line_items[0][price_data][product_data][name]':'霁明测试 · '+m.PLANS[body.plan]['name'],
              'payment_method_types[0]':'alipay' if body.method=='alipay' else 'card'}
        if subscription:
            data.update({'line_items[0][price_data][recurring][interval]':'month','subscription_data[metadata][order_id]':order['id']})
        else:data['payment_intent_data[metadata][order_id]']=order['id']
        session=await p.stripe('POST','checkout/sessions',data,'checkout-'+order['id'])
        url=p.checkout_url(session.get('url'),'stripe')
    else:
        session=await p.paypal('POST','/v2/checkout/orders',{
            'intent':'CAPTURE','purchase_units':[{'reference_id':order['id'],'custom_id':order['id'],
            'amount':{'currency_code':body.currency.upper(),'value':f"{offer['amountMinor']/100:.2f}"}}],
            'application_context':{'return_url':return_url,'cancel_url':return_url,'user_action':'PAY_NOW'}},'checkout-'+order['id'])
        url=p.checkout_url(next((v['href'] for v in session.get('links',[]) if v['rel']=='approve'),None),'paypal')
    e.update_order(order['id'],provider_id=session['id'],checkout_url=url,status='pending')
    return {'orderId':order['id'],'url':url,'testMode':True}


async def stripe_invoice(invoice_id):
    invoice=await p.stripe('GET','invoices/'+p.provider_id(invoice_id))
    sub_id=invoice.get('subscription') or invoice.get('parent',{}).get('subscription_details',{}).get('subscription')
    if not sub_id:raise HTTPException(409,'账单没有订阅关联。')
    sub=await p.stripe('GET','subscriptions/'+p.provider_id(sub_id))
    order=e.get_order(sub.get('metadata',{}).get('order_id',''))
    offer=json.loads(order['quote'])
    if offer['provider']!='stripe' or offer['renewal']!='automatic':raise HTTPException(409,'订阅渠道不匹配。')
    if order['subscription_id'] and order['subscription_id']!=sub_id:raise HTTPException(409,'订阅关联不匹配。')
    items=sub.get('items',{}).get('data',[])
    if len(items)!=1:raise HTTPException(409,'订阅项目数量不匹配。')
    price=items[0].get('price',{})
    if price.get('unit_amount')!=offer['amountMinor'] or price.get('currency')!=offer['currency'] or price.get('recurring',{}).get('interval')!='month' or price.get('recurring',{}).get('interval_count',1)!=1 or items[0].get('quantity',1)!=1:
        raise HTTPException(409,'订阅价格已变化，请人工核对。')
    e.update_order(order['id'],subscription_id=sub_id,customer_id=sub.get('customer'),
                   subscription_status=sub['status'],cancel_at_end=int(bool(sub.get('cancel_at_period_end'))))
    if invoice.get('status')!='paid' or not invoice.get('paid'):return
    lines=invoice.get('lines',{}).get('data',[])
    if len(lines)!=1 or invoice['lines'].get('has_more') or lines[0].get('proration'):
        raise HTTPException(409,'非标准周期账单待人工核对。')
    period=lines[0]['period']
    if invoice.get('amount_paid')!=invoice.get('total'):raise HTTPException(409,'账单未足额支付。')
    e.record_payment(order,invoice['id'],invoice['amount_paid'],invoice['currency'],
        invoice['status_transitions']['paid_at'],period['start'],period['end'])
    if invoice.get('charge'):
        charge=await p.stripe('GET','charges/'+p.provider_id(invoice['charge']))
        if charge.get('amount_refunded'):external_refund('stripe',invoice['id'],charge['amount_refunded'])


async def stripe_session(order):
    if not order['provider_id']:raise HTTPException(409,'结账请求尚未返回，请重试原购买请求。')
    session=await p.stripe('GET','checkout/sessions/'+p.provider_id(order['provider_id']))
    offer=json.loads(order['quote'])
    if session.get('client_reference_id')!=order['id'] or session.get('metadata',{}).get('order_id')!=order['id']:
        raise HTTPException(409,'付款身份关联不匹配。')
    expected_mode='subscription' if offer['renewal']=='automatic' else 'payment'
    if session.get('mode')!=expected_mode:raise HTTPException(409,'付款周期与订单不匹配。')
    if session.get('status')=='expired':
        if order['status']!='paid':e.update_order(order['id'],status='expired')
        return
    if session.get('mode')=='subscription':
        sub_id=session.get('subscription')
        if sub_id:
            sub=await p.stripe('GET','subscriptions/'+p.provider_id(sub_id))
            e.update_order(order['id'],subscription_id=sub_id,customer_id=session.get('customer'),subscription_status=sub['status'],cancel_at_end=int(bool(sub.get('cancel_at_period_end'))))
            if sub.get('latest_invoice'):await stripe_invoice(sub['latest_invoice'])
        return
    if session.get('payment_status')!='paid':return
    intent=await p.stripe('GET','payment_intents/'+p.provider_id(session['payment_intent']))
    if intent.get('status')!='succeeded' or intent.get('metadata',{}).get('order_id')!=order['id']:
        raise HTTPException(409,'付款尚未确认。')
    charge=await p.stripe('GET','charges/'+p.provider_id(intent['latest_charge']))
    if not charge.get('paid') or charge.get('payment_intent')!=intent['id']:raise HTTPException(409,'付款凭证不一致。')
    e.record_payment(order,intent['id'],intent['amount_received'],intent['currency'],charge['created'])
    if charge.get('amount_refunded'):external_refund('stripe',intent['id'],charge['amount_refunded'])


async def paypal_order(order,capture=False):
    ident=p.provider_id(order['provider_id'])
    data=await p.paypal('GET','/v2/checkout/orders/'+ident)
    units=data.get('purchase_units',[])
    if data.get('id')!=ident or len(units)!=1 or units[0].get('custom_id')!=order['id']:
        raise HTTPException(409,'PayPal 订单关联不匹配。')
    offer=json.loads(order['quote']);amount=units[0]['amount']
    if minor(amount['value'])!=offer['amountMinor'] or amount['currency_code'].lower()!=offer['currency']:
        raise HTTPException(409,'PayPal 金额不匹配。')
    if data['status']=='VOIDED':
        if order['status']!='paid':e.update_order(order['id'],status='expired')
        return
    if capture and data['status']=='APPROVED':
        await p.paypal('POST','/v2/checkout/orders/'+ident+'/capture',{},'capture-'+order['id'])
        data=await p.paypal('GET','/v2/checkout/orders/'+ident)
        units=data['purchase_units']
    captures=units[0].get('payments',{}).get('captures',[])
    if not captures:return
    if len(captures)!=1:raise HTTPException(409,'多笔收款需要人工核对。')
    cap=await p.paypal('GET','/v2/payments/captures/'+p.provider_id(captures[0]['id']))
    if cap['status'] not in ('COMPLETED','REFUNDED','PARTIALLY_REFUNDED'):return
    e.record_payment(order,cap['id'],minor(cap['amount']['value']),cap['amount']['currency_code'],iso_epoch(cap['create_time']))
    if cap['status']=='REFUNDED':external_refund('paypal',cap['id'],offer['amountMinor'])
    elif cap['status']=='PARTIALLY_REFUNDED':external_refund('paypal',cap['id'],1)


def external_refund(provider,reference,amount):
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        pay=db.execute('SELECT * FROM billing_payments WHERE provider=? AND reference=?',(provider,reference)).fetchone()
        if not pay:raise HTTPException(409,'退款对应付款尚未同步，稍后重试。')
        full=amount>=pay['amount']
        if pay['state']=='refunded':return
        db.execute('UPDATE billing_payments SET refunded=?,state=? WHERE id=?',
                   (max(amount,pay['refunded']),'refunded' if full else 'partial_refund_review',pay['id']))
        db.execute('UPDATE grants SET revoked=? WHERE id=?',(1 if full else 2,pay['grant_id']))
        if full:db.execute("UPDATE billing_refunds SET status='succeeded' WHERE payment_id=?",(pay['id'],))


@router.post('/orders/{order_id}/refresh')
async def refresh(order_id:str,request:Request):
    user=m.current_user(request,True)
    order=e.get_order(order_id,user['id'])
    m.throttle('billing-refresh:'+user['id'],20,60)
    if json.loads(order['quote'])['provider']=='stripe':await stripe_session(order)
    else:await paypal_order(order,capture=True)
    return e.list_account(user['id'])


@router.post('/orders/{order_id}/cancel-renewal')
async def cancel(order_id:str,request:Request):
    user=m.current_user(request,True)
    order=e.get_order(order_id,user['id'])
    if not order['subscription_id']:raise HTTPException(409,'此订单为单次购买，不会自动续费。')
    sub=await p.stripe('POST','subscriptions/'+p.provider_id(order['subscription_id']),{'cancel_at_period_end':'true'},'cancel-'+order_id)
    e.update_order(order_id,cancel_at_end=int(bool(sub.get('cancel_at_period_end'))),subscription_status=sub['status'])
    return {'ok':True,'message':'已取消自动续费，已付周期仍可使用到期。'}


@router.post('/orders/{order_id}/portal')
async def portal(order_id:str,request:Request):
    user=m.current_user(request,True)
    order=e.get_order(order_id,user['id'])
    if not order['customer_id'] or json.loads(order['quote'])['provider']!='stripe':
        raise HTTPException(409,'此订单没有 Stripe 客户账单入口。')
    data={'customer':p.provider_id(order['customer_id']),'return_url':origin()+'/#membership'}
    configuration=m.config('STRIPE_TEST_PORTAL_CONFIGURATION')
    if not configuration:
        raise HTTPException(503,'请先配置仅允许更新付款方式、查看账单及取消订阅的测试客户门户。')
    data['configuration']=p.provider_id(configuration)
    session=await p.stripe('POST','billing_portal/sessions',data)
    url=session.get('url','');parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname!='billing.stripe.com':raise HTTPException(502,'客户门户地址无效。')
    return {'url':url,'testMode':True}


@router.post('/payments/{payment_id}/refund-request')
def refund_request(payment_id:str,body:RefundRequest,request:Request):
    user=m.current_user(request,True)
    return e.request_refund(user['id'],payment_id,body.reason)


@router.get('/admin/refunds')
def refund_queue(request:Request,response:Response):
    admin(request);response.headers['Cache-Control']='no-store'
    with m.database() as db:
        return {'items':[dict(r) for r in db.execute('SELECT r.*,p.amount,p.currency,p.order_id FROM billing_refunds r JOIN billing_payments p ON p.id=r.payment_id ORDER BY r.created DESC')]}


async def sync_refund(refund,payment):
    if not refund.get('provider_id'):raise HTTPException(409,'渠道退款尚未创建，请重试审核提交。')
    if payment['provider']=='stripe':
        obj=await p.stripe('GET','refunds/'+p.provider_id(refund['provider_id']))
        reference=payment['reference']
        if reference.startswith('in_'):
            invoice=await p.stripe('GET','invoices/'+p.provider_id(reference))
            reference=invoice.get('payment_intent')
        if obj.get('payment_intent')!=reference:raise HTTPException(409,'退款对应的付款不匹配。')
        state={'succeeded':'succeeded','failed':'failed','canceled':'failed'}.get(obj['status'],'pending')
        e.refund_result(refund['id'],obj['id'],state,obj['amount'],obj['currency'])
    else:
        obj=await p.paypal('GET','/v2/payments/refunds/'+p.provider_id(refund['provider_id']))
        if not any(v.get('rel')=='up' and urlparse(v.get('href','')).path=='/v2/payments/captures/'+payment['reference'] for v in obj.get('links',[])):
            raise HTTPException(409,'PayPal 退款对应的收款不匹配。')
        state={'COMPLETED':'succeeded','FAILED':'failed','CANCELLED':'failed'}.get(obj['status'],'pending')
        e.refund_result(refund['id'],obj['id'],state,minor(obj['amount']['value']),obj['amount']['currency_code'])


@router.post('/admin/refunds/{refund_id}/review')
async def review(refund_id:str,body:ReviewRequest,request:Request):
    user=admin(request)
    refund,payment=e.review(refund_id,user['id'],body.approve,body.note)
    if not body.approve or refund['status']=='succeeded':return {'status':refund['status']}
    order=e.get_order(payment['order_id'])
    if order['subscription_id']:
        sub=await p.stripe('POST','subscriptions/'+p.provider_id(order['subscription_id']),{'cancel_at_period_end':'true'},'cancel-'+order['id'])
        e.update_order(order['id'],cancel_at_end=1,subscription_status=sub['status'])
    if not refund.get('provider_id'):
        if payment['provider']=='stripe':
            ref=payment['reference']
            if ref.startswith('in_'):
                invoice=await p.stripe('GET','invoices/'+p.provider_id(ref))
                ref=invoice.get('payment_intent')
            obj=await p.stripe('POST','refunds',{'payment_intent':p.provider_id(ref),'amount':str(payment['amount']),
                                'metadata[refund_id]':refund_id},'refund-'+refund_id)
        else:
            obj=await p.paypal('POST','/v2/payments/captures/'+p.provider_id(payment['reference'])+'/refund',
                    {'amount':{'currency_code':payment['currency'].upper(),'value':f"{payment['amount']/100:.2f}"}},'refund-'+refund_id)
        with m.database() as db:db.execute('UPDATE billing_refunds SET provider_id=? WHERE id=?',(obj['id'],refund_id))
        refund['provider_id']=obj['id']
    await sync_refund(refund,payment)
    return {'ok':True}


@router.post('/admin/refunds/{refund_id}/refresh')
async def refresh_refund(refund_id:str,request:Request):
    admin(request)
    with m.database() as db:
        refund=db.execute('SELECT * FROM billing_refunds WHERE id=?',(refund_id,)).fetchone()
        if not refund:raise HTTPException(404,'退款申请不存在。')
        payment=db.execute('SELECT * FROM billing_payments WHERE id=?',(refund['payment_id'],)).fetchone()
    await sync_refund(dict(refund),dict(payment))
    return {'ok':True}


@router.post('/webhooks/stripe')
async def stripe_webhook(request:Request):
    raw=await request.body()
    if len(raw)>1_000_000:raise HTTPException(413,'回调过大。')
    event=p.verify_stripe(raw,request.headers.get('stripe-signature',''))
    with m.database() as db:
        if db.execute("SELECT 1 FROM billing_events WHERE provider='stripe' AND id=?",(event['id'],)).fetchone():return {'received':True}
    obj=event['data']['object'];kind=event['type']
    if kind.startswith('checkout.session.'):
        session=await p.stripe('GET','checkout/sessions/'+p.provider_id(obj['id']))
        order=e.get_order(session.get('metadata',{}).get('order_id',''))
        if order['provider_id'] and order['provider_id']!=session['id']:raise HTTPException(409,'结账编号不匹配。')
        e.update_order(order['id'],provider_id=session['id'])
        await stripe_session(e.get_order(order['id']))
    elif kind in ('invoice.paid','invoice.payment_failed'):
        await stripe_invoice(obj['id'])
    elif kind.startswith('customer.subscription.'):
        sub=await p.stripe('GET','subscriptions/'+p.provider_id(obj['id']))
        order=e.get_order(sub.get('metadata',{}).get('order_id',''))
        if order['subscription_id'] and order['subscription_id']!=sub['id']:raise HTTPException(409,'订阅编号不匹配。')
        e.update_order(order['id'],subscription_id=sub['id'],subscription_status=sub['status'],cancel_at_end=int(bool(sub.get('cancel_at_period_end'))))
    elif kind.startswith('refund.'):
        obj=await p.stripe('GET','refunds/'+p.provider_id(obj['id']))
        rid=obj.get('metadata',{}).get('refund_id')
        if rid:
            with m.database() as db:
                refund=db.execute('SELECT * FROM billing_refunds WHERE id=?',(rid,)).fetchone()
                payment=db.execute('SELECT * FROM billing_payments WHERE id=?',(refund['payment_id'],)).fetchone() if refund else None
            if not refund:raise HTTPException(409,'退款记录尚未就绪。')
            await sync_refund({**dict(refund),'provider_id':obj['id']},dict(payment))
    elif kind=='charge.refunded':
        charge=await p.stripe('GET','charges/'+p.provider_id(obj['id']))
        external_refund('stripe',charge.get('invoice') or charge['payment_intent'],charge['amount_refunded'])
    with m.database() as db:db.execute('INSERT OR IGNORE INTO billing_events VALUES (?,?,?)',('stripe',event['id'],time.time()))
    return {'received':True}


@router.post('/webhooks/paypal')
async def paypal_webhook(request:Request):
    raw=await request.body()
    if len(raw)>1_000_000:raise HTTPException(413,'回调过大。')
    event=await p.verify_paypal(raw,request.headers)
    with m.database() as db:
        if db.execute("SELECT 1 FROM billing_events WHERE provider='paypal' AND id=?",(event['id'],)).fetchone():return {'received':True}
    resource=event['resource'];kind=event['event_type']
    if kind in ('CHECKOUT.ORDER.APPROVED','PAYMENT.CAPTURE.COMPLETED','PAYMENT.CAPTURE.REFUNDED','PAYMENT.CAPTURE.DENIED','PAYMENT.CAPTURE.PENDING'):
        oid=resource.get('id') if kind=='CHECKOUT.ORDER.APPROVED' else resource.get('supplementary_data',{}).get('related_ids',{}).get('order_id')
        with m.database() as db:
            order=db.execute('SELECT * FROM billing_orders WHERE provider_id=?',(oid,)).fetchone() if oid else None
            refund=db.execute('SELECT * FROM billing_refunds WHERE provider_id=?',(resource.get('id'),)).fetchone()
            payment=db.execute('SELECT * FROM billing_payments WHERE id=?',(refund['payment_id'],)).fetchone() if refund else None
        if not order and oid:
            remote=await p.paypal('GET','/v2/checkout/orders/'+p.provider_id(oid))
            units=remote.get('purchase_units',[])
            if len(units)!=1:raise HTTPException(409,'PayPal 订单项目不匹配。')
            order=e.get_order(units[0].get('custom_id',''))
            if order['provider_id'] and order['provider_id']!=oid:raise HTTPException(409,'PayPal 订单关联冲突。')
            if json.loads(order['quote'])['provider']!='paypal':raise HTTPException(409,'付款渠道不匹配。')
            e.update_order(order['id'],provider_id=oid)
            order=e.get_order(order['id'])
        if order:await paypal_order(dict(order),capture=kind=='CHECKOUT.ORDER.APPROVED')
        elif refund:await sync_refund(dict(refund),dict(payment))
        elif kind=='PAYMENT.CAPTURE.REFUNDED':
            obj=await p.paypal('GET','/v2/payments/refunds/'+p.provider_id(resource['id']))
            capture_id=next((urlparse(link.get('href','')).path.rsplit('/',1)[-1] for link in obj.get('links',[])
                             if link.get('rel')=='up' and urlparse(link.get('href','')).path.startswith('/v2/payments/captures/')),None)
            with m.database() as db:
                pay=db.execute("SELECT * FROM billing_payments WHERE provider='paypal' AND reference=?",(capture_id,)).fetchone()
            if not pay:raise HTTPException(409,'退款关联尚未同步，请稍后重试。')
            await paypal_order(e.get_order(pay['order_id']))
    with m.database() as db:db.execute('INSERT OR IGNORE INTO billing_events VALUES (?,?,?)',('paypal',event['id'],time.time()))
    return {'received':True}
