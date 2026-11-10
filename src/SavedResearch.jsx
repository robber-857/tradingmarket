import {useState,useEffect} from 'react';
import {memberRequest} from './member-api';
export default function SavedResearch(){
  const [items,setItems]=useState([]),[error,setError]=useState(''),[opened,setOpened]=useState(null);
  const load=()=>memberRequest('/api/account/saved').then(d=>setItems(d.items)).catch(e=>setError(e.message));
  useEffect(()=>{load();},[]);
  async function remove(id){if(!window.confirm('删除这条已保存研究？此操作不会删除原始市场数据。'))return;try{await memberRequest('/api/account/saved/'+id,{method:'DELETE'});setOpened(null);await load();}catch(e){setError(e.message);}}
  return <section className="panel"><h3>已保存研究</h3><p className="fine-print">保存的是当时的分析与假设。旧报告不是最新行情，AI 会话暂不支持跨重启续接。</p>{error&&<p role="alert">{error}</p>}<div className="member-saved-list">{items.filter(i=>i.kind==='research').map(i=><article key={i.id}><strong>{i.title}</strong><p className="fine-print">{new Date(i.updated*1000).toLocaleString()}</p><button className="button" onClick={()=>setOpened(opened===i.id?null:i.id)}>{opened===i.id?'收起':'查看历史'}</button> <button className="button" onClick={()=>remove(i.id)}>删除</button>{opened===i.id&&<div>{i.payload.turns?.map((t,n)=><div key={n}><h4>{t.question||'研究解读'}</h4><p>{t.answer?.conclusion?.text}</p>{t.answer?.insights?.map((v,j)=><p key={j}>{v.text}</p>)}</div>)}<details><summary>查看保存的假设和证据</summary><pre>{JSON.stringify(i.payload,null,2)}</pre></details></div>}</article>)}</div>{!items.length&&!error&&<p>在财报／估值 AI 解读中点击「保存研究」，即可在这里回顾。</p>}</section>;
}
