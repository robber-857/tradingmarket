import {useEffect,useRef,useState} from 'react';
import {memberRequest} from './member-api';
import {CreditCard, Wallet, ArrowUpRight, Check, ReceiptText} from 'lucide-react';

const cash=(n,c)=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:c.toUpperCase()}).format(n/100);
const stateNames={creating:'创建中',pending:'待渠道确认',paid:'已付款',expired:'订单已过期',refunded:'已退款',partial_refund_review:'部分退款待核对',requested:'申请待审核',processing:'提交渠道中',succeeded:'退款成功',failed:'退款失败',rejected:'申请已拒绝'};
export default function BillingPanel({account,catalog,currency,onCurrencyChange,selection,onRefresh,onLogin}){
  const [status,setStatus]=useState(null),[records,setRecords]=useState(null),[plan,setPlan]=useState('research'),[period,setPeriod]=useState('month');
  const [method,setMethod]=useState(currency==='cny'?'alipay':'card'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [refundId,setRefundId]=useState(null),[reason,setReason]=useState(''),[queue,setQueue]=useState([]),[note,setNote]=useState('');
  const checkoutKey=useRef(null),returnPromise=useRef(null);
  const [quote,setQuote]=useState(null),[quoteError,setQuoteError]=useState('');
  const signature=JSON.stringify({plan,currency,period,method});
  useEffect(()=>{
    let alive=true;setQuote(null);setQuoteError('');
    if(account?.user&&(currency==='cny'?method==='alipay':method!=='alipay'))memberRequest('/api/billing/quote',{method:'POST',body:signature}).then(value=>alive&&setQuote({signature,value})).catch(e=>alive&&setQuoteError(e.message));
    return()=>{alive=false;};
  },[signature,account?.user?.id]);
  useEffect(()=>{setMethod(currency==='cny'?'alipay':'card');checkoutKey.current=null;},[currency]);
  useEffect(()=>{if(selection){setPlan(selection.plan);setPeriod(selection.period);checkoutKey.current=null;}},[selection]);
  async function load(){const d=await memberRequest('/api/billing/account');setRecords(d);if(d.isAdmin&&status?.enabled)setQueue((await memberRequest('/api/billing/admin/refunds')).items);}
  useEffect(()=>{
    let alive=true;
    memberRequest('/api/billing/status').then(d=>alive&&setStatus(d)).catch(e=>alive&&setError(e.message));
    const id=new URLSearchParams(location.search).get('billing_order');
    if(account?.user){
      if(id&&/^ord_[a-f0-9]{32}$/.test(id)&&!returnPromise.current){
        history.replaceState(null,'',location.pathname+'#membership');
        returnPromise.current=memberRequest('/api/billing/orders/'+id+'/refresh',{method:'POST'});
      }
      (returnPromise.current||Promise.resolve()).then(()=>{if(alive){load().catch(e=>setError(e.message));onRefresh();}}).catch(e=>alive&&setError(e.message));
    }
    return()=>{alive=false;};
  },[account?.user?.id]);
  useEffect(()=>{if(records?.isAdmin&&status?.enabled)memberRequest('/api/billing/admin/refunds').then(d=>setQueue(d.items)).catch(e=>setError(e.message));},[records?.isAdmin,status?.enabled]);
  async function act(fn){setBusy(true);setError('');setMessage('');try{await fn();await load();await onRefresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function checkout(){if(busy||quote?.signature!==signature)return;await act(async()=>{
    const signature=JSON.stringify({plan,currency,period,method});
    if(checkoutKey.current?.signature!==signature)checkoutKey.current={signature,key:crypto.randomUUID()};
    const data=await memberRequest('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan,currency,period,method,request_key:checkoutKey.current.key})});
    window.location.assign(data.url);
  });}
  const provider=method==='paypal'?'paypal':'stripe';
  const chosen=catalog?.plans.find(p=>p.id===plan);
  const preview=period==='week'?catalog?.weekPass:chosen;
  const validQuote=quote?.signature===signature?quote.value:null;
  const price=validQuote?.amountMinor??preview?.prices[currency];
  const methods=currency==='cny'?[['alipay','支付宝','人民币 · 单次购买']]:[['card','银行卡','信用卡 / 借记卡'],['apple_pay','Apple Pay','通过 Stripe 结账'],['paypal','PayPal','Sandbox 测试账户']];
  const active=account?.plan&&account.plan!=='free';
  return <section className="billing-panel member-billing" id="billing">
    <div className="member-pricing-heading"><div><span className="eyebrow">BILLING & PAYMENTS</span><h2>付款与账单</h2><p>确认方案和付款方式，订单以支付渠道返回的结果为准。</p></div><span className="member-test-label">仅测试，不收取真实款项</span></div>
    <div className="member-checkout-layout"><div className="member-checkout-fields">
      <h3><span>01</span>确认会员方案</h3><div className="billing-fields">
        <label>套餐<select value={plan} disabled={busy} onChange={e=>{setPlan(e.target.value);if(e.target.value!=='research')setPeriod('month');}}>{[['research','研究会员'],['advanced','高级会员'],['expert','专家会员']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
        <label>周期<select value={period} disabled={busy} onChange={e=>setPeriod(e.target.value)}><option value="month">一个月</option>{plan==='research'&&<option value="week">七天 · 不自动续费</option>}</select></label>
        <label>付款币种<select value={currency} disabled={busy} onChange={e=>onCurrencyChange(e.target.value)}><option value="cny">人民币 CNY</option><option value="aud">澳元 AUD</option><option value="usd">美元 USD</option></select></label>
      </div>
      <h3><span>02</span>选择付款方式</h3><div className="member-payment-methods" role="group" aria-label="付款方式">{methods.map(([id,label,desc])=><button key={id} type="button" aria-pressed={method===id} disabled={busy} onClick={()=>setMethod(id)}><span className="member-method-icon">{id==='card'?<CreditCard size={21}/>:<Wallet size={21}/>}</span><span><b>{label}</b><small>{desc}</small></span><span className="member-radio">{method===id&&<Check size={11}/>}</span></button>)}</div>
      <p className="fine-print">{currency==='cny'?'人民币使用支付宝。银行卡、Apple Pay 和 PayPal 可切换至 AUD 或 USD。':'银行卡和 Apple Pay 由 Stripe 处理；Apple Pay 是否显示取决于结账环境与设备。'}</p>
    </div><aside className="member-order-summary"><span className="eyebrow">方案汇总</span><h3>{period==='week'?'七天研究通行证':chosen?.name||'研究会员'}</h3><div className="member-summary-price">{price!=null?cash(price,currency):'—'}<small> / {period==='week'?'7 天':'月'}</small></div><div className="member-summary-lines"><span>普通 AI <b>{preview?.limits.ai??'—'} 次</b></span><span>深度分析 <b>{preview?.limits.deep??'—'} 次</b></span><span>续费方式 <b>{period==='week'||method==='alipay'||method==='paypal'?'到期手动续购':'每月自动续费'}</b></span></div>
      {account?.user?<button className="member-plan-cta is-primary" disabled={busy||!status?.[provider]||!validQuote||active} onClick={checkout}>{busy?'正在处理…':active?'请先管理当前会员':'前往测试结账'}<ArrowUpRight size={16}/></button>:<button className="member-plan-cta is-primary" onClick={onLogin}>登录后继续<ArrowUpRight size={16}/></button>}
      <p className="fine-print">{active?'已有有效会员，暂不支持重复购买或中途换档。':!status?.[provider]?'此付款渠道尚未完成测试配置，结账暂不可用。':'将前往支付渠道的测试结账页。付款确认后才开通权益。'}</p>{quoteError&&<p role="alert" className="home-error">{quoteError}</p>}
    </aside></div>
    <details className="member-refund-policy"><summary>续费与退款规则</summary><p>每笔付款后七天内，且未使用该周期付费 AI、深度分析或会员课程，可申请审核后全额原路退款。申请后暂停该周期权益。取消自动续费不会取消已付周期。支付宝、PayPal 与七天通行证均为单次购买。</p></details>
    {message&&<p role="status" className="member-notice">{message}</p>}{error&&<p role="alert" className="home-error">{error}</p>}
    {account?.user&&<>
      <div className="member-billing-records"><h4><ReceiptText size={17}/>订单与续费</h4>{records&&!records.orders.length&&<p className="member-records-empty">还没有订单。选择会员后，可在这里查看付款与续费状态。</p>}<div className="member-saved-list">{records?.orders.map(o=><article key={o.id}><strong>{cash(o.quote.amountMinor,o.quote.currency)} · {o.quote.period==='week'?'七天':'月度'} · {o.quote.method}</strong><p>{stateNames[o.status]||o.status} · {o.quote.renewal==='manual'?'单次购买':o.cancel_at_end?'已取消自动续费':'自动续费订阅'}</p><small>{o.id}</small><div className="billing-actions"><button className="button" disabled={busy||!o.provider_id} onClick={()=>act(async()=>{await memberRequest('/api/billing/orders/'+o.id+'/refresh',{method:'POST'});setMessage('已向支付渠道核对订单状态。');})}>核对付款状态</button>{o.customer_id&&<button className="button" disabled={busy} onClick={()=>act(async()=>{const d=await memberRequest('/api/billing/orders/'+o.id+'/portal',{method:'POST'});window.location.assign(d.url);})}>账单与付款方式</button>}{o.subscription_id&&!o.cancel_at_end&&o.subscription_status!=='canceled'&&<button className="button" disabled={busy} onClick={()=>act(async()=>{const d=await memberRequest('/api/billing/orders/'+o.id+'/cancel-renewal',{method:'POST'});setMessage(d.message);})}>取消自动续费</button>}</div></article>)}</div>
      <h4>付款记录与退款申请</h4>{records&&!records.payments.length&&<p className="member-records-empty">暂无付款记录。</p>}<div className="member-saved-list">{records?.payments.map(pay=><article key={pay.id}><strong>{cash(pay.amount,pay.currency)} · {new Date(pay.paid_at*1000).toLocaleString()}</strong><p>权益截止：{new Date(pay.end*1000).toLocaleString()} · {stateNames[pay.state]||pay.state}</p>{pay.refund?<p>退款：{stateNames[pay.refund.status]||pay.refund.status}{pay.refund.note?' · '+pay.refund.note:''}</p>:<><button className="button" disabled={!pay.refundable||busy} onClick={()=>{setRefundId(pay.id);setReason('');}}>申请退款</button>{!pay.refundable&&<p className="fine-print">{pay.refundUnavailableReason}</p>}</>}
      {refundId===pay.id&&<form onSubmit={ev=>{ev.preventDefault();act(async()=>{await memberRequest('/api/billing/payments/'+pay.id+'/refund-request',{method:'POST',body:JSON.stringify({reason})});setRefundId(null);setMessage('退款申请已提交，该周期权益暂时冻结，等待审核。');});}}><label>退款原因<textarea required minLength={3} maxLength={1000} value={reason} onChange={ev=>setReason(ev.target.value)}/></label><button className="button" disabled={busy}>提交申请并暂停该周期权益</button></form>}</article>)}</div>
      {records?.isAdmin&&status?.enabled&&<div><h4>测试退款审核</h4><label>审核说明<input value={note} onChange={ev=>setNote(ev.target.value)} maxLength={1000}/></label>{queue.map(r=><article className="billing-review" key={r.id}><strong>{cash(r.amount,r.currency)} · {stateNames[r.status]||r.status}</strong><p>{r.reason}</p><small>{r.id}</small><div className="billing-actions">{['requested','processing','pending'].includes(r.status)&&<button className="button" disabled={busy||note.trim().length<3} onClick={()=>act(()=>memberRequest('/api/billing/admin/refunds/'+r.id+'/review',{method:'POST',body:JSON.stringify({approve:true,note})}))}>批准／重试测试退款</button>}{['requested','failed'].includes(r.status)&&<button className="button" disabled={busy||note.trim().length<3} onClick={()=>act(()=>memberRequest('/api/billing/admin/refunds/'+r.id+'/review',{method:'POST',body:JSON.stringify({approve:false,note})}))}>拒绝并恢复权益</button>}{r.provider_id&&<button className="button" disabled={busy} onClick={()=>act(()=>memberRequest('/api/billing/admin/refunds/'+r.id+'/refresh',{method:'POST'}))}>核对渠道退款</button>}</div></article>)}</div>}
    </div></>}
  </section>;
}
