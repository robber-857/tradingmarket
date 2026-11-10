"""Durable test orders, paid-period grants, refund eligibility and audit state."""
import calendar
from datetime import datetime, timezone
import json
import time
from fastapi import HTTPException
from . import membership as m


def next_month(stamp):
    dt=datetime.fromtimestamp(stamp,timezone.utc)
    year=dt.year+(dt.month==12);month=dt.month%12+1
    return dt.replace(year=year,month=month,day=min(dt.day,calendar.monthrange(year,month)[1])).timestamp()


def get_order(order_id,user_id=None):
    with m.database() as db:
        row=db.execute('SELECT * FROM billing_orders WHERE id=?',(order_id,)).fetchone()
    if not row or (user_id and row['user_id']!=user_id):raise HTTPException(404,'订单不存在。')
    return dict(row)


def new_order(user_id,offer,key):
    ident='ord_'+m.digest(user_id+key)[:32]
    encoded=json.dumps(offer,sort_keys=True)
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM billing_orders WHERE id=?',(ident,)).fetchone()
        if existing:
            if existing['quote']!=encoded:raise HTTPException(409,'请求编号已用于其他套餐。')
            return dict(existing)
        current=db.execute("SELECT 1 FROM grants WHERE user_id=? AND end>? AND revoked=0",(user_id,time.time())).fetchone()
        sub=db.execute("SELECT 1 FROM billing_orders WHERE user_id=? AND subscription_id IS NOT NULL AND subscription_status NOT IN ('canceled','incomplete_expired')",(user_id,)).fetchone()
        if current or sub:raise HTTPException(409,'已有有效会员或未结束的订阅，请先管理当前订阅；暂不支持重复购买和中途换档。')
        pending=db.execute("SELECT * FROM billing_orders WHERE user_id=? AND status IN ('creating','pending')",(user_id,)).fetchone()
        if pending:
            if pending['quote']==encoded:return dict(pending)
            raise HTTPException(409,'还有待支付订单，请先完成或核实该订单的关闭状态。')
        db.execute('INSERT INTO billing_orders(id,user_id,quote,status,created) VALUES (?,?,?,?,?)',
                   (ident,user_id,encoded,'creating',time.time()))
    return get_order(ident,user_id)


def update_order(ident,**fields):
    allowed={'status','provider_id','checkout_url','subscription_id','customer_id','subscription_status','cancel_at_end'}
    if not fields or not fields.keys()<=allowed:raise ValueError('Invalid order fields')
    with m.database() as db:
        db.execute('UPDATE billing_orders SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),ident))


def record_payment(order,reference,amount,currency,paid_at,start=None,end=None):
    offer=json.loads(order['quote'])
    if amount!=offer['amountMinor'] or currency.lower()!=offer['currency']:
        raise HTTPException(409,'付款金额或币种与订单不一致，待人工核对。')
    start=start or paid_at
    end=end or (start+7*86400 if offer['period']=='week' else next_month(start))
    if not (0<paid_at<=time.time()+300 and 0<start<end and end-start<=32*86400):
        raise HTTPException(409,'付款周期无效。')
    payment_id='pay_'+m.digest(offer['provider']+reference)[:32]
    grant_id='test:'+payment_id
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM billing_payments WHERE id=?',(payment_id,)).fetchone()
        if old:
            if old['order_id']!=order['id'] or old['amount']!=amount or old['currency']!=currency.lower():
                raise HTTPException(409,'付款记录冲突。')
            return payment_id
        db.execute('INSERT INTO billing_payments(id,provider,reference,order_id,amount,currency,paid_at,start,end,grant_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (payment_id,offer['provider'],reference,order['id'],amount,currency.lower(),paid_at,start,end,grant_id))
        db.execute('INSERT INTO grants VALUES (?,?,?,?,?,?,0)',
                   (grant_id,order['user_id'],offer['plan'],start,end,json.dumps(offer['limits'])))
        db.execute("UPDATE billing_orders SET status='paid' WHERE id=?",(order['id'],))
    return payment_id


def unused(db,payment):
    spent=db.execute("SELECT 1 FROM usage WHERE period=? AND state IN ('pending','complete') LIMIT 1",(payment['grant_id'],)).fetchone()
    read=db.execute('SELECT 1 FROM benefit_reads WHERE grant_id=? LIMIT 1',(payment['grant_id'],)).fetchone()
    return not spent and not read


def eligible(db,payment,now=None):
    now=now or time.time()
    if payment['state']!='paid' or payment['refunded']:
        return False,'该付款已有退款或异常状态。'
    if now-payment['paid_at']>7*86400:return False,'已超过付款后七天。'
    if not unused(db,payment):return False,'已使用付费 AI、深度分析或会员课程，或有分析仍在处理中。'
    return True,''


def request_refund(user_id,payment_id,reason):
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        payment=db.execute('SELECT p.* FROM billing_payments p JOIN billing_orders o ON o.id=p.order_id WHERE p.id=? AND o.user_id=?',
                           (payment_id,user_id)).fetchone()
        if not payment:raise HTTPException(404,'付款记录不存在。')
        old=db.execute('SELECT * FROM billing_refunds WHERE payment_id=?',(payment_id,)).fetchone()
        if old:return dict(old)
        ok,why=eligible(db,payment)
        if not ok:raise HTTPException(409,why)
        refund_id='rf_'+m.digest(payment_id)[:32]
        db.execute('INSERT INTO billing_refunds(id,payment_id,reason,status,created) VALUES (?,?,?,?,?)',
                   (refund_id,payment_id,reason,'requested',time.time()))
        # Hold this period before admitting any new paid AI/course usage.
        db.execute('UPDATE grants SET revoked=2 WHERE id=?',(payment['grant_id'],))
    return {'id':refund_id,'status':'requested'}


def review(refund_id,admin,approve,note):
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM billing_refunds WHERE id=?',(refund_id,)).fetchone()
        if not row:raise HTTPException(404,'退款申请不存在。')
        payment=db.execute('SELECT * FROM billing_payments WHERE id=?',(row['payment_id'],)).fetchone()
        if row['status'] in ('processing','pending','succeeded'):
            if not approve:raise HTTPException(409,'退款已提交渠道，不能撤销审核。')
            return dict(row),dict(payment)
        if row['status']=='failed' and approve:
            raise HTTPException(409,'渠道退款已失败，请先核对渠道状态；可拒绝申请恢复权益。')
        if row['status'] not in ('requested','failed'):raise HTTPException(409,'该申请已处理。')
        # Window eligibility was frozen at application time; reviewing later is allowed.
        if approve and not unused(db,payment):raise HTTPException(409,'该周期已使用付费权益，不能批准退款。')
        status='processing' if approve else 'rejected'
        db.execute('UPDATE billing_refunds SET status=?,reviewer=?,reviewed_at=?,note=? WHERE id=?',
                   (status,admin,time.time(),note,refund_id))
        if not approve:db.execute('UPDATE grants SET revoked=0 WHERE id=? AND revoked=2',(payment['grant_id'],))
    return {**dict(row),'status':status},dict(payment)


def refund_result(refund_id,provider_id,status,amount,currency):
    with m.database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT r.*,p.amount,p.currency,p.grant_id FROM billing_refunds r JOIN billing_payments p ON p.id=r.payment_id WHERE r.id=?',(refund_id,)).fetchone()
        if not row:raise HTTPException(404,'退款申请不存在。')
        if row['amount']!=amount or row['currency']!=currency.lower():raise HTTPException(409,'退款金额或币种不匹配。')
        if row['status']=='succeeded':return
        db.execute('UPDATE billing_refunds SET provider_id=?,status=? WHERE id=?',(provider_id,status,refund_id))
        if status=='succeeded':
            db.execute("UPDATE billing_payments SET state='refunded',refunded=amount WHERE id=?",(row['payment_id'],))
            db.execute('UPDATE grants SET revoked=1 WHERE id=?',(row['grant_id'],))
        # Failed refunds stay held pending explicit admin rejection/restoration.


def list_account(user_id):
    with m.database() as db:
        orders=[dict(r) for r in db.execute('SELECT * FROM billing_orders WHERE user_id=? ORDER BY created DESC',(user_id,))]
        payments=[]
        for row in db.execute('SELECT p.* FROM billing_payments p JOIN billing_orders o ON o.id=p.order_id WHERE o.user_id=? ORDER BY paid_at DESC',(user_id,)):
            p=dict(row);p['refundable'],p['refundUnavailableReason']=eligible(db,row)
            refund=db.execute('SELECT id,status,created,note FROM billing_refunds WHERE payment_id=?',(p['id'],)).fetchone()
            p['refund']=dict(refund) if refund else None
            payments.append(p)
    for o in orders:o['quote']=json.loads(o['quote'])
    return {'orders':orders,'payments':payments,'testMode':True}
