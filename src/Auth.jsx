import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,Mail,CheckCircle2} from 'lucide-react';
import {BrandLogo} from './BrandMark';
import {memberRequest} from './member-api';
import {subscribeAuthChange} from './auth-state';
import './auth.css';

const routes=new Set(['overview','financials','fundamentals','news','calendar','daily','options','strategies','watchlist','academy','membership','admin','settings','capital']);
export const safeNext=value=>routes.has(value)?value:'overview';
export function loginHref(next=location.hash.slice(1).split('?')[0]){return '#login?next='+encodeURIComponent(safeNext(next));}
const errors={google_failed:'Google 验证未完成，请重新登录。',google_cancelled:'已取消 Google 登录，你也可以使用邮箱。',google_unavailable:'Google 登录尚未配置，请使用邮箱。',email_link_required:'请使用邮箱验证链接登录此账户。'};

export default function Auth(){
  const [params]=useState(()=>new URLSearchParams(location.hash.split('?')[1]));
  const next=safeNext(params.get('next'));
  const [mode,setMode]=useState(location.hash.startsWith('#register')?'register':'login');
  const [config,setConfig]=useState(null),[email,setEmail]=useState(''),[phone,setPhone]=useState('');
  const [error,setError]=useState(errors[params.get('error')]||''),[message,setMessage]=useState(''),[link,setLink]=useState(''),[busy,setBusy]=useState(false);
  const verification=useRef(null);
  useEffect(()=>{
    let active=true;
    const unsubscribe=subscribeAuthChange(async event=>{
      try{const account=event?.account||await memberRequest('/api/account');if(active&&account.user)location.hash=next;}
      catch{/* Keep the form available when a background session check fails. */}
    });
    return()=>{active=false;unsubscribe();};
  },[next]);
  useEffect(()=>{
    let alive=true;
    memberRequest('/api/auth/config').then(x=>alive&&setConfig(x)).catch(e=>alive&&setError(e.message));
    const token=params.get('token');
    if(token&&!verification.current){
      history.replaceState(null,'',loginHref(next));
      setBusy(true);
      verification.current=memberRequest('/api/auth/verify',{method:'POST',body:JSON.stringify({token})});
    }
    const operation=verification.current||memberRequest('/api/account');
    operation.then(x=>{if(alive&&x.user){location.hash=safeNext(x.next||next);}}).catch(e=>alive&&setError(e.message)).finally(()=>alive&&setBusy(false));
    return()=>{alive=false;};
  },[]);
  async function submit(e){
    e.preventDefault();setBusy(true);setError('');setMessage('');setLink('');
    try{const result=await memberRequest('/api/auth/request-link',{method:'POST',body:JSON.stringify({email,phone:mode==='register'?phone:'',intent:mode,next})});setMessage(result.message);setLink(result.localLoginUrl||'');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <main className="auth-page"><a className="auth-back" href={'#'+next}><ArrowLeft size={16}/>返回研究工作台</a><div className="auth-layout"><aside className="auth-story"><BrandLogo/><span className="eyebrow">RESEARCH WITH CLARITY</span><h1>看懂信息，<br/>形成自己的判断。</h1><p>从财报到基本面，把数据读成有依据的研究。</p><div className="auth-editorial"><span>你的研究，从这里继续</span><strong>财报解读 · 基本面分析 · 研究归档</strong><p>登录后保存研究，管理关注，随时回来继续探索。</p></div></aside><section className="auth-form-panel" aria-labelledby="auth-title"><div className="auth-tabs" role="group" aria-label="账户操作">{[['login','登录'],['register','注册']].map(([id,label])=><button key={id} disabled={busy} aria-pressed={mode===id} onClick={()=>{setMode(id);setError('');setMessage('');setLink('');}}>{label}</button>)}</div><h2 id="auth-title">{mode==='login'?'欢迎回来':'创建你的霁明账户'}</h2><p>{mode==='login'?'登录，继续你的市场研究。':'邮箱为必填，手机号选填。'}</p><button className="auth-google" disabled={!config?.google||busy} onClick={()=>location.assign('/api/auth/google/start?next='+encodeURIComponent(next))}><span aria-hidden="true">G</span>使用 Google 账户继续<ArrowRight size={17}/></button>{config&&!config.google&&<small className="auth-help">Google 登录准备中，当前可使用邮箱验证。</small>}<div className="auth-divider"><span>或使用邮箱</span></div><form onSubmit={submit}><label htmlFor="auth-email">电子邮箱 <span>必填</span></label><input id="auth-email" type="email" autoComplete="email" maxLength={254} required placeholder="you@example.com" value={email} disabled={busy} onChange={e=>setEmail(e.target.value)}/>{mode==='register'&&<><label htmlFor="auth-phone">手机号码 <span>选填</span></label><input id="auth-phone" type="tel" autoComplete="tel" maxLength={30} placeholder="例如 +61 412 345 678" value={phone} disabled={busy} onChange={e=>setPhone(e.target.value)}/></>}<p className="auth-help">我们会发送一次性验证链接，无需设置密码。验证邮箱后即可进入工作台。</p><button className="auth-submit" disabled={!config?.email||busy}><Mail size={17}/>{busy?'正在处理…':mode==='register'?'验证邮箱并注册':'发送登录链接'}<ArrowRight size={17}/></button></form>{config&&!config.email&&<p className="auth-help">邮箱登录暂未开放，请稍后再试。</p>}{error&&<p role="alert" className="auth-error">{error}</p>}{message&&<div role="status" className="auth-success"><CheckCircle2 size={18}/><p>{message}</p></div>}{link&&<a className="auth-local" href={link} onClick={async e=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{const token=new URLSearchParams(new URL(link).hash.split('?')[1]).get('token');const account=await memberRequest('/api/auth/verify',{method:'POST',body:JSON.stringify({token})});location.hash=safeNext(account.next);}catch(err){setError(err.message);}finally{setBusy(false);}}}>打开本机验证链接 →</a>}<footer>登录后按账户权限使用 AI 分析、云端研究和会员内容。 <a href="/privacy.html" target="_blank" rel="noreferrer">隐私说明</a></footer></section></div></main>;
}
