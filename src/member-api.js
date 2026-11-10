import {notifyAuthChange, getAccountSnapshot, getAuthRevision, rememberAccount} from './auth-state.js';

let hasCheckedAccount=false;

let accountRead=null;
export function memberRequest(url, options={}) {
  if(url!=='/api/account') return performRequest(url,options);
  const revision=getAuthRevision();
  if(accountRead?.revision===revision) return accountRead.promise;
  const read={revision};
  read.promise=performRequest(url,options).finally(()=>{if(accountRead===read)accountRead=null;});
  accountRead=read;
  return read.promise;
}

async function performRequest(url, options={}) {
  const revision=getAuthRevision();
  const response=await fetch(url,{cache:'no-store',...options,headers:{'Content-Type':'application/json',...options.headers}});
  const data=await response.json();
  if(response.status===401 && !location.hash.startsWith('#login')) location.hash='#login?next='+encodeURIComponent(location.hash.slice(1).split('?')[0]||'overview');
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'服务暂时不可用，请稍后重试。');
  if(url==='/api/auth/verify') notifyAuthChange(data);
  if(url==='/api/auth/logout') notifyAuthChange({user:null,plan:'free',planName:'未登录'});
  if(url==='/api/account') {
    if(revision!==getAuthRevision()) return getAccountSnapshot() ?? memberRequest(url,options);
    const initial=!hasCheckedAccount;
    hasCheckedAccount=true;
    rememberAccount(data,revision);
    // OAuth returns to a fresh document; wake the original login tab too.
    if(initial&&data.user) notifyAuthChange(data);
  }
  return data;
}
