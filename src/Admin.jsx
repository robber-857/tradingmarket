import {useEffect, useRef, useState} from 'react';
import {memberRequest} from './member-api';
import './membership.css';
import PaymentOperations from './PaymentOperations';

const names={free:'免费体验',research:'研究会员',advanced:'高级会员',expert:'专家会员'};
const stamp=value=>value?new Date(value*1000).toLocaleString('zh-CN'):'无到期日';
const actionNames={create_account:'添加账号',grant_membership:'开通会员',revoke_membership:'撤销手动授权',billing_reconcile:'核对测试付款'};

export default function Admin(){
  const [access,setAccess]=useState(null),[data,setData]=useState(null),[detail,setDetail]=useState(null);
  const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[offset,setOffset]=useState(0),[version,setVersion]=useState(0);
  const [email,setEmail]=useState(''),[plan,setPlan]=useState('research'),[days,setDays]=useState(30),[reason,setReason]=useState('');
  const [revokeReason,setRevokeReason]=useState(''),[revoking,setRevoking]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const attempt=useRef(null),selection=useRef(0);
  useEffect(()=>{let active=true;memberRequest('/api/account').then(x=>active&&setAccess(x)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[]);
  useEffect(()=>{
    if(!access?.isAdmin)return;
    let active=true;setData(null);
    memberRequest(`/api/admin/users?q=${encodeURIComponent(search)}&offset=${offset}`).then(x=>active&&setData(x)).catch(e=>active&&setError(e.message));
    return()=>{active=false;};
  },[access,search,offset,version]);
  async function inspect(id){
    const seq=++selection.current;setDetail(null);setRevoking(null);setRevokeReason('');
    const result=await memberRequest('/api/admin/users/'+encodeURIComponent(id));
    if(seq===selection.current)setDetail(result);
  }
  async function provision(e){
    e.preventDefault();if(busy)return;setBusy(true);setError('');setMessage('');
    const fields={email,plan,days:Number(days),reason};const fingerprint=JSON.stringify(fields);
    if(attempt.current?.fingerprint!==fingerprint)attempt.current={fingerprint,key:crypto.randomUUID()};
    try{
      const result=await memberRequest('/api/admin/users',{method:'POST',body:JSON.stringify({...fields,request_key:attempt.current.key})});
      attempt.current=null;setVersion(v=>v+1);await inspect(result.userId);
      setMessage(plan==='free'?'账号已添加；已有账号的权益保持不变。':'会员已开通，用户用该邮箱登录即可使用。');setReason('');
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function revoke(id){
    if(busy)return;setBusy(true);setError('');setMessage('');
    try{await memberRequest('/api/admin/grants/'+encodeURIComponent(id)+'/revoke',{method:'POST',body:JSON.stringify({reason:revokeReason})});await inspect(detail.account.user.id);setVersion(v=>v+1);setMessage('手动授权已撤销，账号与保存记录仍保留。');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  if(!access)return <div role="status">{error||'正在验证管理员身份…'}</div>;
  if(!access.isAdmin)return <section className="panel admin-denied"><h2>管理员后台</h2><p>{access.user?'当前账号没有管理权限，请使用管理员邮箱登录。':'请先使用管理员邮箱登录。'}</p><a className="button" href="#membership">前往会员与账户</a></section>;
  return <div className="membership-page admin-page">
    <div className="admin-heading"><div><span className="eyebrow">ACCOUNT ADMINISTRATION</span><h2>账号与会员管理</h2><p>添加用户、开通会员和管理手动授权。</p></div><a className="button" href="#membership">我的账户 / 付款管理</a></div>
    {error&&<p className="home-error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <section className="panel"><h3>添加账号 / 开通会员</h3><form onSubmit={provision} className="admin-form">
      <label>用户邮箱<input type="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@example.com"/></label>
      <label>会员权限<select value={plan} onChange={e=>setPlan(e.target.value)}>{Object.entries(names).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
      <label>有效天数<input type="number" min="1" max="366" step="1" required disabled={plan==='free'} value={days} onChange={e=>setDays(e.target.value)}/></label>
      <label className="admin-reason">开通原因<input required minLength={3} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)} placeholder="例如：内测体验、线下已付款"/></label>
      <p className="fine-print admin-reason">{plan==='free'?'仅创建免费账号，不改变已有会员。':'立即生效，本次有效期共用该等级的一份 AI 额度，不按月叠加。高级 / 专家会员可阅读会员课程。'} 手动开通不会扣款，也不会授予后台管理权限。用户自行通过邮箱登录，本操作不发送邮件。</p>
      <button className="button primary" disabled={busy||reason.trim().length<3}>{busy?'处理中…':plan==='free'?'添加免费账号':'开通会员'}</button>
    </form></section>
    <section className="panel"><div className="admin-heading"><h3>用户列表 {data?`· ${data.total}`:''}</h3><form className="member-login" onSubmit={e=>{e.preventDefault();setSearch(query);setOffset(0);setVersion(v=>v+1);}}><input aria-label="搜索用户邮箱" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索邮箱"/><button className="button">搜索</button></form></div>
      <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>邮箱</th><th>当前会员</th><th>到期时间</th><th>操作</th></tr></thead><tbody>{data?.items.map(u=><tr key={u.id}><td>{u.email}</td><td>{names[u.plan]}</td><td>{stamp(u.expiresAt)}</td><td><button className="button" disabled={busy} onClick={()=>{setEmail(u.email);inspect(u.id).catch(e=>setError(e.message));}}>管理</button></td></tr>)}</tbody></table></div>
      {!data?<p role="status">正在加载用户…</p>:!data.items.length&&<p>没有匹配的账号。</p>}
      <div className="billing-actions"><button className="button" disabled={offset===0||busy} onClick={()=>setOffset(v=>Math.max(0,v-25))}>上一页</button><button className="button" disabled={!data||offset+25>=data.total||busy} onClick={()=>setOffset(v=>v+25)}>下一页</button></div>
    </section>
    <PaymentOperations/>
    {detail&&<section className="panel"><h3>{detail.account.user.email}</h3><p>{detail.account.planName} · 到期：{stamp(detail.account.expiresAt)}</p>
      <div className="member-usage">{Object.entries(detail.account.usage).filter(([k])=>k!=='sentiment').map(([key,value])=><div key={key}><span>{key==='ai'?'普通 AI 剩余':'深度分析剩余'}</span><strong>{value.remaining} / {value.limit}</strong></div>)}</div>
      <h4>授权记录</h4>{!detail.grants.length&&<p>暂无会员授权。</p>}{detail.grants.map(g=><article className="billing-review" key={g.id}><b>{names[g.plan]} · {g.manual?'手动开通':'付款授权'}</b><p>{stamp(g.start)} — {stamp(g.end)} · {g.revoked?'已撤销 / 冻结':g.end<=Date.now()/1000?'已到期':'有效'}</p>{g.reason&&<p>原因：{g.reason}</p>}
        {g.manual&&!g.revoked&&g.end>Date.now()/1000&&(revoking===g.id?<div className="admin-revoke"><label>撤销原因<input value={revokeReason} maxLength={500} onChange={e=>setRevokeReason(e.target.value)} placeholder="至少三个字"/></label><p className="fine-print">确认后立即停止此笔手动授权；如需重新开通，将开始新的额度周期。</p><div className="billing-actions"><button className="button" disabled={busy||revokeReason.trim().length<3} onClick={()=>revoke(g.id)}>确认撤销授权</button><button className="button" disabled={busy} onClick={()=>setRevoking(null)}>取消</button></div></div>:<button className="button" disabled={busy} onClick={()=>setRevoking(g.id)}>撤销此笔授权</button>)}
      </article>)}
      <h4>最近操作记录</h4>{detail.actions.map(a=><article className="billing-review" key={a.id}><b>{actionNames[a.action]}</b><p>{a.detail.reason}</p><small>{stamp(a.created)} · {a.actor_email}</small></article>)}
    </section>}
  </div>;
}
