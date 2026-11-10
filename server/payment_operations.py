"""Test payment readiness and audited reconciliation; never fabricate settlement."""
import json
import time
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from . import membership as m, payment_providers as providers, billing, billing_engine
from .admin_api import audit, note

router = APIRouter(prefix='/api/admin/billing')


def readiness():
    checks = []
    rules = [
        ('BILLING_TEST_ENABLED', lambda v: v == '1', '测试支付开关'),
        ('STRIPE_TEST_SECRET_KEY', lambda v: v.startswith('sk_test_'), 'Stripe 测试密钥'),
        ('STRIPE_TEST_WEBHOOK_SECRET', lambda v: v.startswith('whsec_'), 'Stripe 回调验签'),
        ('STRIPE_TEST_PORTAL_CONFIGURATION', lambda v: v.startswith('bpc_'), 'Stripe 测试账单门户'),
        ('PAYPAL_SANDBOX_CLIENT_ID', bool, 'PayPal Sandbox Client ID'),
        ('PAYPAL_SANDBOX_CLIENT_SECRET', bool, 'PayPal Sandbox Secret'),
        ('PAYPAL_SANDBOX_WEBHOOK_ID', bool, 'PayPal Sandbox Webhook ID'),
        ('BILLING_ADMIN_USER_IDS', lambda v: any(x.strip() for x in v.split(',')), '退款审核管理员'),
    ]
    for key, valid, label in rules:
        value = m.config(key)
        state = 'ready' if valid(value) else ('missing' if not value else 'invalid')
        if key == 'BILLING_TEST_ENABLED' and value != '1':
            state = 'disabled'
        checks.append({'key': key, 'label': label, 'state': state})
    states = {c['key']: c['state'] == 'ready' for c in checks}
    stripe = all(states[k] for k in ('BILLING_TEST_ENABLED','STRIPE_TEST_SECRET_KEY','STRIPE_TEST_WEBHOOK_SECRET'))
    paypal = all(states[k] for k in ('BILLING_TEST_ENABLED','PAYPAL_SANDBOX_CLIENT_ID','PAYPAL_SANDBOX_CLIENT_SECRET','PAYPAL_SANDBOX_WEBHOOK_ID'))
    return {'testMode': True, 'salesEnabled': False, 'checks': checks,
            'channels': {'card': stripe, 'apple_pay': stripe, 'alipay': stripe, 'paypal': paypal},
            'credentialsVerified': False, 'webhookDeliveryVerified': False,
            'notice': '仅检查服务端配置存在性与格式，不代表商户权限、支付宝通道、设备钱包或回调投递已验证。'}


def operator(request):
    user = m.current_user(request, True)
    ids = {v.strip() for v in m.config('BILLING_ADMIN_USER_IDS').split(',') if v.strip()}
    if not m.is_admin(user) and user['id'] not in ids:
        raise HTTPException(403, '需要支付核对管理员权限。')
    return user


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=3, max_length=500)


@router.get('/readiness')
def config_status(request: Request, response: Response):
    operator(request)
    response.headers['Cache-Control'] = 'no-store'
    return readiness()


@router.get('/orders')
def orders(request: Request, response: Response, min_age_minutes: int = Query(15, ge=0, le=525600),
           offset: int = Query(0, ge=0)):
    operator(request)
    response.headers['Cache-Control'] = 'no-store'
    cutoff = time.time()-min_age_minutes*60
    with m.database() as db:
        total = db.execute("SELECT count(*) FROM billing_orders WHERE status IN ('creating','pending') AND created<=?", (cutoff,)).fetchone()[0]
        rows = db.execute("SELECT o.*,u.email FROM billing_orders o JOIN users u ON u.id=o.user_id "
                          "WHERE o.status IN ('creating','pending') AND o.created<=? ORDER BY o.created,o.id LIMIT 25 OFFSET ?",
                          (cutoff,offset)).fetchall()
        items = []
        for row in rows:
            offer = json.loads(row['quote'])
            items.append({'id': row['id'], 'email': row['email'], 'created': row['created'], 'status': row['status'],
                          'provider': offer['provider'], 'method': offer['method'], 'plan': offer['plan'],
                          'amountMinor': offer['amountMinor'], 'currency': offer['currency'],
                          'canReconcile': bool(row['provider_id']),
                          'needsProviderLookup': not bool(row['provider_id'])})
        history = [dict(r) for r in db.execute(
            "SELECT a.id,a.created,a.detail,u.email AS actor_email FROM admin_actions a JOIN users u ON u.id=a.actor_id "
            "WHERE a.action='billing_reconcile' ORDER BY a.created DESC LIMIT 20")]
    for entry in history:
        entry['detail'] = json.loads(entry['detail'])
    return {'items': items, 'total': total, 'offset': offset, 'pageSize': 25, 'history': history}


@router.post('/orders/{order_id}/reconcile')
async def reconcile(order_id: str, body: ReconcileRequest, request: Request, response: Response):
    actor = operator(request)
    response.headers['Cache-Control'] = 'no-store'
    reason = note(body.reason)
    m.throttle('admin-billing-reconcile:'+actor['id'],20,60)
    order = billing_engine.get_order(order_id)
    if not order['provider_id']:
        raise HTTPException(409, '渠道订单编号缺失，请先在渠道后台核对原创建请求；不能手动标记付款或强制关闭。')
    provider = json.loads(order['quote'])['provider']
    providers.require(provider)
    error = None
    try:
        if provider == 'stripe':
            await billing.stripe_session(order)
        else:
            # Operator reconciliation observes existing captures; it never captures an approved order.
            await billing.paypal_order(order, capture=False)
    except HTTPException as exc:
        error = exc
    except Exception:
        error = HTTPException(502, '渠道核对未完成，请稍后重试；订单未被手动确认。')
    after = billing_engine.get_order(order_id)
    with m.database() as db:
        audit(db, actor, order['user_id'], 'billing_reconcile',
              {'orderId': order_id, 'provider': provider, 'reason': reason,
               'before': order['status'], 'after': after['status'],
               'outcome': 'failed' if error else 'checked', 'errorStatus': error.status_code if error else None})
    if error:
        raise error
    return {'orderId': order_id, 'status': after['status'], 'testMode': True,
            'message': '已读取渠道状态并同步可验证的结果；未发起扣款或退款。'}


if __name__ == '__main__':
    print(json.dumps(readiness(), ensure_ascii=False, indent=2))
