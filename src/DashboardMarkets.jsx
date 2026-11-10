import {useEffect,useState} from 'react';
import {ArrowUpRight,Check,ChevronLeft,ChevronRight,SlidersHorizontal} from 'lucide-react';
import {readJson} from './EvidenceAnswer';

export const DEFAULT_MARKETS=['nasdaq100','gold','bitcoin','sp500'];
const choices=[['nasdaq100','Nasdaq 100'],['gold','黄金'],['bitcoin','BTC'],['sp500','标普 500'],['silver','白银'],['treasury10y','美国 10 年期国债收益率'],['dollar','美元指数'],['vix','VIX']];
const storageKey='meridian.dashboard.markets.v1';
const number=(n,d=2)=>Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
export function Pager({page,total,size,onChange,label}){
  const pages=Math.max(1,Math.ceil(total/size)),current=Math.min(page,pages-1);
  if(total<=size)return null;
  return <nav className="home-pager" aria-label={`${label}分页`}><span>共 {total} 项</span><div><button aria-label={`${label}上一页`} disabled={current===0} onClick={()=>onChange(current-1)}><ChevronLeft size={15}/></button><span aria-live="polite">{current+1} / {pages}</span><button aria-label={`${label}下一页`} disabled={current===pages-1} onClick={()=>onChange(current+1)}><ChevronRight size={15}/></button></div></nav>;
}
export function pageItems(items,page,size){return items.slice(Math.min(page,Math.max(0,Math.ceil(items.length/size)-1))*size, (Math.min(page,Math.max(0,Math.ceil(items.length/size)-1))+1)*size);}
function Sparkline({items,name}){
  if(items.length<2)return <div className="overview-market-spark-empty">历史走势暂不可用</div>;
  const values=items.map(p=>p.value),lo=Math.min(...values),hi=Math.max(...values);
  const points=values.map((v,i)=>`${i/(values.length-1)*240},${42-(v-lo)/(hi-lo||1)*36}`).join(' ');
  return <svg className="overview-market-sparkline" viewBox="0 0 240 48" preserveAspectRatio="none" role="img" aria-label={`${name}近一个月日线走势`}><path d="M0 46H240" className="overview-market-spark-baseline"/><polyline points={points}/></svg>;
}
export default function DashboardMarkets({refresh,timezone}){
  const [selected,setSelected]=useState(()=>{try{const v=JSON.parse(localStorage.getItem(storageKey));return Array.isArray(v)?[...new Set(v.filter(id=>choices.some(([k])=>id===k)))]:DEFAULT_MARKETS;}catch{return DEFAULT_MARKETS;}});
  const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[editing,setEditing]=useState(false),[page,setPage]=useState(0),[storageError,setStorageError]=useState(false);
  useEffect(()=>{try{localStorage.setItem(storageKey,JSON.stringify(selected));setStorageError(false);}catch{setStorageError(true);}},[selected]);
  useEffect(()=>{
    const controller=new AbortController();let disposed=false;
    async function load(){setLoading(true);try{const result=await fetch('/api/market/overview',{signal:controller.signal}).then(readJson);if(!disposed){setData(result);setError('');}}catch(e){if(!disposed&&e.name!=='AbortError')setError('行情更新失败，请稍后刷新。');}finally{if(!disposed)setLoading(false);}}
    load();const timer=setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
    return()=>{disposed=true;controller.abort();clearInterval(timer);};
  },[refresh]);
  const toggle=id=>{setSelected(s=>s.includes(id)?s.filter(k=>k!==id):[...s,id]);setPage(0);};
  return <section className="panel dashboard-markets" aria-label="关注市场行情">
    <div className="panel-title"><div><h2>关注市场</h2><p>主要指数与跨资产行情 · 近一个月走势</p></div><button className="button" aria-expanded={editing} aria-controls="overview-market-picker" onClick={()=>setEditing(v=>!v)}><SlidersHorizontal size={14}/>自选指标</button></div>
    {editing&&<div className="overview-market-picker" id="overview-market-picker"><div><strong>选择要关注的市场</strong><button className="home-text-action" onClick={()=>{setSelected([...DEFAULT_MARKETS]);setPage(0);}}>恢复默认</button></div><div className="overview-market-picker-options">{choices.map(([id,label])=><button key={id} aria-pressed={selected.includes(id)} onClick={()=>toggle(id)}><span className="overview-market-check">{selected.includes(id)&&<Check size={12}/>}</span>{label}</button>)}</div><small>{storageError?'浏览器无法保存设置，本次选择仅在当前页面有效。':'选择自动保存在当前浏览器。'}</small><button className="home-text-action" onClick={()=>setEditing(false)}>完成</button></div>}
    {error&&<p className="home-error" role="alert">{error}{data?' 当前保留上次结果。':''}</p>}
    <div className="overview-market-quotes">{pageItems(selected,page,4).map(id=>{
      const item=data?.items.find(i=>i.id===id),available=item?.available,change=item?.change;
      const tone=error||item?.stale?'muted':change==null||change===0?'flat':change>0?'up':'down';
      const yieldQuote=id==='treasury10y';
      return <article className={`overview-market-quote ${tone}`} key={id}>
        <div className="overview-market-quote-heading"><h3>{choices.find(([k])=>k===id)[1]}</h3>{item&&<a href={item.sourceUrl} aria-label={`查看${item.name}行情来源`} target="_blank" rel="noreferrer"><ArrowUpRight size={14}/></a>}</div>
        <p className="overview-market-instrument">{item?.description||'正在读取行情'}{item?.unit&&` · ${item.unit}`}</p>
        <strong className="overview-market-price">{available?number(item.price,yieldQuote?3:2):'—'}{available&&yieldQuote&&<small>%</small>}</strong>
        <div className="overview-market-change">{change!=null?<><span>{change>0?'+':''}{number(yieldQuote?change*100:change)}{yieldQuote?' bp':''}</span>{!yieldQuote&&<span>({change>0?'+':''}{number(item.changePct)}%)</span>}</>:<span>{loading?'读取中…':'涨跌数据暂缺'}</span>}<small>{change!=null?'较前收盘':''}</small></div>
        <Sparkline items={item?.history||[]} name={item?.name||id}/>
        <div className="overview-market-quote-time">{item?.asOf?new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(item.asOf)):'尚未取得报价'}<span>{error||item?.stale?'更新失败 · 缓存':!available?loading?'读取中':'暂不可用':item?.quoteOld?'较早报价':'参考行情'}</span></div>
      </article>;
    })}</div>
    {!selected.length&&<p className="home-empty">还没有关注的市场。点击“自选指标”添加，或恢复默认四项。</p>}
    <Pager page={page} total={selected.length} size={4} onChange={setPage} label="关注市场"/>
    <p className="home-footnote">{data?.notice||'参考行情可能延迟，来源：Yahoo Finance。缺失数据保留为空。'} 来源：Yahoo Finance · 报价时间按当前所选时区显示。</p>
  </section>;
}
