import {useEffect, useRef, useState} from 'react';
import './membership.css';
import SavedResearch from './SavedResearch';
import {memberRequest} from './member-api';
import {subscribeAuthChange, getAccountSnapshot} from './auth-state';
import BillingPanel from './BillingPanel';
import {ArrowRight, Check, Sparkles, ShieldCheck, BookOpen, Clock3, UserRound, LogOut, CreditCard} from 'lucide-react';
import './membership-design.css';

const money=(value,currency)=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:currency.toUpperCase(),maximumFractionDigits:0}).format(value/100);
export default function Membership(){
  const [catalog,setCatalog]=useState(null),[account,setAccount]=useState(getAccountSnapshot),[currency,setCurrency]=useState('usd');
  const [email,setEmail]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[link,setLink]=useState(''),[busy,setBusy]=useState(false);
  const loginPromise=useRef(null);
  const [selection,setSelection]=useState(null);
  const [tab,setTab]=useState(()=>new URLSearchParams(location.search).has('billing_order')?'billing':'plans');
  const refresh=()=>memberRequest('/api/account').then(setAccount);
  useEffect(()=>{
    let active=true, revision=0;
    const reload=async event=>{
      const current=++revision;
      if(event?.account){setAccount(event.account);return;}
      try{const data=await memberRequest('/api/account');if(active&&current===revision)setAccount(data);}
      catch(e){if(active&&current===revision)setError(e.message);}
    };
    const unsubscribe=subscribeAuthChange(reload);
    if(!new URLSearchParams(location.hash.split('?')[1]).has('token'))reload();
    return()=>{active=false;unsubscribe();};
  },[]);
  useEffect(()=>{
    let alive=true;
    memberRequest('/api/membership/plans').then(x=>alive&&setCatalog(x)).catch(e=>alive&&setError(e.message));
    const token=new URLSearchParams(location.hash.split('?')[1]).get('token');
    if(token&&!loginPromise.current){
      history.replaceState(null,'','#membership');
      loginPromise.current=memberRequest('/api/auth/verify',{method:'POST',body:JSON.stringify({token})});
    }
    if(loginPromise.current){
      loginPromise.current.then(x=>{if(alive){setAccount(x);setMessage('已登录，会员额度与研究记录属于此账户。');}}).catch(e=>alive&&setError(e.message));
    }
    return()=>{alive=false;};
  },[]);
  async function login(e){e.preventDefault();setBusy(true);setError('');setLink('');try{const d=await memberRequest('/api/auth/request-link',{method:'POST',body:JSON.stringify({email})});setMessage(d.message);setLink(d.localLoginUrl||'');}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function logout(){setBusy(true);try{await memberRequest('/api/auth/logout',{method:'POST'});setLink('');setMessage('已退出登录。');}catch(e){setError(e.message);}finally{setBusy(false);}}
  function switchTab(next){setTab(next);requestAnimationFrame(()=>document.querySelector('.member-tabs')?.scrollIntoView({behavior:'smooth',block:'start'}));}
  function choose(plan,period='month'){setSelection({plan,period});switchTab('billing');}
  const plans=catalog?.plans.filter(p=>p.id!=='free')||[];
  const free=catalog?.plans.find(p=>p.id==='free');
  const loginDisabled=catalog?.emailLoginEnabled===false;
  const descriptions={research:'适合持续跟踪市场、建立研究习惯。',advanced:'把市场研究与系统学习放在一起。',expert:'为多标的跟踪和高频研究留出余量。'};
  const icons={research:BookOpen,advanced:Sparkles,expert:ShieldCheck};
  const focusLogin=()=>{location.hash='login?next=membership';};
  return <div className="membership-page member-center">
    {error&&<p className="home-error" role="alert">{error}</p>}{message&&<p className="member-notice" role="status">{message}</p>}
    <section className="member-account-strip" id="member-account" aria-label="我的账户">
      <span className="member-account-icon"><UserRound size={21}/></span>
      {account===null?<div className="member-account-identity" role="status"><strong>正在确认登录状态…</strong><span>请稍候</span></div>:account.user?<>
        <div className="member-account-identity"><strong>{account.planName}</strong><span>{account.user.email}</span><small>{account.expiresAt?'有效至 '+new Date(account.expiresAt*1000).toLocaleDateString('zh-CN'):'免费额度按 UTC 自然月重置'}</small></div>
        <div className="member-account-meters">{Object.entries(account.usage).filter(([k])=>k!=='sentiment').map(([key,v])=><div key={key}><span>{key==='ai'?'普通 AI':'深度分析'}<b>{v.remaining}<small> / {v.limit}</small></b></span><progress max={Math.max(1,v.limit)} value={v.remaining} aria-label={`${key==='ai'?'普通 AI':'深度分析'}剩余额度`}/></div>)}</div>
        <div className="member-account-actions">{account.isAdmin&&<a className="button" href="#admin">管理后台</a>}<button className="icon-button" aria-label="退出登录" title="退出登录" disabled={busy} onClick={logout}><LogOut size={17}/></button></div>
      </>:<>
        <div className="member-account-identity"><strong>登录，开始你的研究</strong><span>管理 AI 额度与已保存的研究</span></div>
        <div className="member-inline-login"><a className="button primary" href="#login?next=membership">登录账户<ArrowRight size={15}/></a><a className="button" href="#register?next=membership">免费注册</a></div>
      </>}
      {account&&!account.user&&<div className="member-login-note"><small>{loginDisabled?'当前可浏览公开研究内容；账号登录开放后，可使用 AI 分析与云端研究保存。':<>首次登录自动创建免费账户。{catalog?.localMode?'本机模式使用一次性登录链接。':'登录链接有效期十五分钟。'}</>}</small>{link&&<a className="button" href={link} onClick={()=>{window.location.href=link;window.location.reload();}}>使用本地一次性链接登录</a>}</div>}
    </section>
    <nav className="member-tabs" aria-label="会员中心导航">{[['plans','会员方案'],['billing','付款与账单'],['research','研究记录']].map(([id,label])=><button key={id} type="button" aria-current={tab===id?'page':undefined} onClick={()=>switchTab(id)}>{label}</button>)}<span><span className="member-test-dot"/>仅测试 · 正式收款未开放</span></nav>
    <div hidden={tab!=='plans'} className="member-tab-content">
      <div className="member-pricing-heading"><div><span className="eyebrow">CLARORA MEMBERSHIP</span><h2>选择你的会员方案</h2><p>同样的证据标准，适合不同研究频率的额度与课程。</p></div><div className="member-currency-switch" role="group" aria-label="选择价格货币">{[['cny','CNY','人民币'],['aud','AUD','澳元'],['usd','USD','美元']].map(([id,label,title])=><button key={id} aria-label={title+' '+label} aria-pressed={currency===id} onClick={()=>setCurrency(id)}>{label}</button>)}</div></div>
      {!catalog?<div className="member-loading" role="status">{error?'会员方案暂时不可用，请刷新重试。':'正在读取会员方案…'}</div>:<div className="member-pricing-grid">{plans.map(plan=>{const Icon=icons[plan.id];const current=account?.plan===plan.id;return <article className={`member-price-card ${plan.id==='advanced'?'is-featured':''}`} key={plan.id}>
        <div className="member-price-cap"><div className="member-tier"><span className="member-tier-icon"><Icon size={19}/></span><span>{current?'当前会员':plan.id==='advanced'?'研究 + 学习':plan.id==='expert'?'高频研究':'日常研究'}</span></div><h3>{plan.name}</h3><p className="member-plan-description">{descriptions[plan.id]}</p><div className="member-price-amount"><strong>{money(plan.prices[currency],currency)}</strong><span>/ 月</span></div><button className={`member-plan-cta ${plan.id==='advanced'?'is-primary':''}`} onClick={()=>current?switchTab('billing'):choose(plan.id)}>{current?'管理当前会员':'选择'+plan.name}<ArrowRight size={16}/></button></div>
        <div className="member-price-benefits"><span className="member-feature-heading">每个会员周期包含</span><ul><li><Check size={14}/><span><b>{plan.limits.ai}</b> 次普通 AI 解读与追问</span></li><li><Check size={14}/><span><b>{plan.limits.deep}</b> 次深度分析</span></li><li><Check size={14}/><span>{plan.all_courses?'全部会员课程':'免费入门课程'}</span></li><li><Check size={14}/><span>研究归档与关注清单保存</span></li></ul><p>{plan.id==='expert'?'更高用量，不包含人工专家咨询。':plan.all_courses?'课程在会员有效期内开放。':'覆盖财报、宏观、新闻与期权研究。'}</p></div>
      </article>;})}</div>}
      <p className="member-pricing-footnote">试行价格 · 以所选币种固定计价 · 额度不滚存 · 会员课程目前含样课，完整内容仍在准备</p>
      {catalog&&<div className="member-starter-options"><article><div><span className="member-option-label">先从免费开始</span><h3>免费体验 <strong>{money(0,currency)}</strong></h3><p>每自然月 {free?.limits.ai} 次普通 AI · {free?.limits.deep} 次深度分析 · 免费课程</p></div><button className="button" onClick={account?.user?()=>{location.hash='financials';}:focusLogin}>{account?.user?'开始研究':'免费注册'}<ArrowRight size={15}/></button></article><article><div><span className="member-option-label">短期体验</span><h3>七天研究通行证 <strong>{money(catalog.weekPass.prices[currency],currency)}</strong></h3><p>{catalog.weekPass.limits.ai} 次普通 AI · {catalog.weekPass.limits.deep} 次深度分析 · 不自动续费</p></div><button className="button" onClick={()=>choose('research','week')}>选择七天<ArrowRight size={15}/></button></article></div>}
      <div className="member-payment-strip"><span><CreditCard size={16}/>测试付款方式</span><span>银行卡</span><span>Apple Pay</span><span>支付宝</span><span>PayPal</span><small>银行卡 / Apple Pay / PayPal：AUD、USD · 支付宝：CNY</small></div>
      <section className="member-faq"><div><span className="eyebrow">MEMBERSHIP GUIDE</span><h3>选择之前，了解这些</h3><p>权益、用量与付款规则。</p></div><div className="member-faq-items">
        <details><summary>深度分析和普通解读有什么不同？</summary><p>目前使用同一模型。深度模式投入更多推理预算，重点检查反例、关键假设、证据缺口和结论失效条件。两种模式都基于当前证据，不包含额外全网检索，也不保证结论一定正确。</p></details>
        <details><summary>追问怎么算次数？</summary><p>追问沿用当前会话继续研究。每次成功的普通解读或追问扣一次普通额度；深度模式只扣一次深度额度。失败不扣次；处理中会预留一次额度。阅读历史、公共简报和确定性计算不扣次数。</p></details>
        <details><summary>会自动续费吗？可以退款吗？</summary><p>银行卡 / Apple Pay 月付为自动续费；七天通行证、支付宝和 PayPal 为单次购买。每笔付款后七天内且未使用该笔付费权益，可申请审核后全额原路退款。取消续费保留已付周期。</p></details>
        <details><summary>市场情绪与课程现在能用吗？</summary><p>市场情绪的付费数据服务尚未接入，规划额度不计入当前可用权益、不扣费。学院现有免费样课及会员验证样课，完整课程内容仍需上线验收。</p></details>
      </div></section>
    </div>
    <div hidden={tab!=='billing'} className="member-tab-content"><BillingPanel key={'billing-'+(account?.user?.id||'anonymous')} account={account} catalog={catalog} currency={currency} onCurrencyChange={setCurrency} selection={selection} onRefresh={refresh} onLogin={focusLogin}/></div>
    <div hidden={tab!=='research'} className="member-tab-content">{account?.user?<SavedResearch key={account.user.id}/>:<section className="member-empty"><BookOpen size={28}/><h3>把研究留在你的账户里</h3><p>登录后可回顾已保存的财报与估值分析。</p><button className="button" onClick={focusLogin}>先登录账户<ArrowRight size={15}/></button></section>}</div>
  </div>;
}
