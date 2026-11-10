import {useEffect,useState} from 'react';
import {memberRequest} from './member-api';

const stateNames={ready:'已填写',missing:'缺少配置',invalid:'格式不符',disabled:'未启用'};
export default function PaymentOperations(){
  const [readiness,setReadiness]=useState(null),[orders,setOrders]=useState(null),[recent,setRecent]=useState(false),[offset,setOffset]=useState(0);
  const [reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const url=`/api/admin/billing/orders?min_age_minutes=${recent?0:15}&offset=${offset}`;
  useEffect(()=>{let alive=true;Promise.all([memberRequest('/api/admin/billing/readiness'),memberRequest(url)]).then(([r,o])=>{if(alive){setReadiness(r);setOrders(o);setError('');}}).catch(e=>alive&&setError(e.message));return()=>{alive=false;};},[url]);
  async function refresh(){setBusy(true);setError('');try{setReadiness(await memberRequest('/api/admin/billing/readiness'));setOrders(await memberRequest(url));}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function reconcile(id){setBusy(true);setError('');setMessage('');try{const result=await memberRequest('/api/admin/billing/orders/'+id+'/reconcile',{method:'POST',body:JSON.stringify({reason})});setMessage(result.message);setOrders(await memberRequest(url));}catch(e){setError(e.message);memberRequest(url).then(setOrders).catch(()=>{});}finally{setBusy(false);}}
  return <section className="panel payment-operations"><div className="admin-heading"><div><h3>测试支付检查</h3><p className="fine-print">配置检查、待确认订单与渠道核对记录。</p></div><button className="button" disabled={busy} onClick={refresh}>刷新检查</button></div>
    {error&&<p className="home-error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {readiness&&<><div className="payment-readiness">{readiness.checks.map(c=><div key={c.key}><span>{c.label}<small>{c.key}</small></span><b className={c.state==='ready'?'is-ready':''}>{stateNames[c.state]}</b></div>)}</div><p className="fine-print">{readiness.notice} 密钥只在服务端 .env 填写；此处不会显示配置值。银行卡 / Apple Pay / 支付宝使用 Stripe 测试通道。</p></>}
    <details className="payment-pending" open><summary>待确认订单 {orders?`· ${orders.total}`:''}</summary><p className="fine-print">默认显示超过十五分钟的订单。核对只读取渠道状态，不发起新的扣款或退款；没有付款凭证不会开通权益。</p><label className="payment-recent"><input type="checkbox" checked={recent} onChange={e=>{setRecent(e.target.checked);setOffset(0);}}/>包含最近十五分钟</label>
      {!!orders?.items.length&&<label>核对原因<input value={reason} maxLength={500} onChange={e=>setReason(e.target.value)} placeholder="例如：用户反馈付款后未到账"/></label>}
      {orders?.items.map(o=><article className="billing-review" key={o.id}><strong>{o.email} · {new Intl.NumberFormat('zh-CN',{style:'currency',currency:o.currency.toUpperCase()}).format(o.amountMinor/100)}</strong><p>{o.method} · {o.status==='creating'?'创建结果待确认':'等待渠道确认'} · {new Date(o.created*1000).toLocaleString('zh-CN')}</p><small>{o.id}</small><div className="billing-actions"><button className="button" disabled={busy||!o.canReconcile||reason.trim().length<3||!readiness?.channels[o.method]} onClick={()=>reconcile(o.id)}>向渠道核对</button></div>{o.needsProviderLookup&&<p className="fine-print">缺少渠道订单编号，需先在渠道后台查询原创建请求，不能强制标记成功或关闭。</p>}</article>)}
      {orders&&!orders.items.length&&<p className="fine-print">当前没有符合条件的待确认订单。</p>}
      {(orders?.total>25||offset>0)&&<div className="billing-actions"><button className="button" disabled={!offset||busy} onClick={()=>setOffset(v=>Math.max(0,v-25))}>上一页</button><button className="button" disabled={offset+25>=orders.total||busy} onClick={()=>setOffset(v=>v+25)}>下一页</button></div>}
    </details>
    {!!orders?.history.length&&<details><summary>最近二十次渠道核对</summary>{orders.history.map(h=><article className="billing-review" key={h.id}><strong>{h.detail.outcome==='checked'?'已核对':'核对未完成'}</strong><p>{h.detail.orderId} · {h.detail.before} → {h.detail.after}</p><p>{h.detail.reason}</p><small>{new Date(h.created*1000).toLocaleString('zh-CN')} · {h.actor_email}</small></article>)}</details>}
  </section>;
}
