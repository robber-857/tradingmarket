import {customerMessage} from './customer-message';
import { useEffect, useRef, useState } from "react";
import { Search, ArrowRight, RefreshCw } from "lucide-react";
import "./stock-search.css";

const featured = [["AAPL","苹果"],["NVDA","英伟达"],["TSLA","特斯拉"],["AMD","AMD"],["AMZN","亚马逊"],["MSFT","微软"]];
export default function StockSearch({symbol, onSelect}) {
  const [query,setQuery]=useState("");
  const [open,setOpen]=useState(false);
  const [results,setResults]=useState([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [meta,setMeta]=useState(null);
  const [active,setActive]=useState(-1);
  const root=useRef(null);
  const input=useRef(null);
  const [recent,setRecent]=useState(()=>{
    try { const value=JSON.parse(localStorage.getItem("meridian-recent-stocks")||"[]");return Array.isArray(value) ? value.filter((s)=>typeof s==="string" && /^[A-Z][A-Z0-9.-]{0,14}$/.test(s)).slice(0,6) : []; }
    catch {return [];}
  });
  useEffect(()=>{
    const close=(e)=>{if(!root.current?.contains(e.target))setOpen(false);};
    document.addEventListener("pointerdown",close);return()=>document.removeEventListener("pointerdown",close);
  },[]);
  useEffect(()=>{
    if(!open)return;
    const c=new AbortController();setBusy(true);setError("");setResults([]);setActive(-1);
    const timer=setTimeout(async()=>{
      try {
        const r=await fetch(`/api/research/assets?q=${encodeURIComponent(query.trim())}`,{signal:c.signal});
        const data=await r.json();
        if(!r.ok)throw new Error(typeof data.detail==="string"?data.detail:"股票目录暂不可用。");
        if(!c.signal.aborted){setResults(data.results);setMeta(data);}
      } catch(e){if(!c.signal.aborted)setError(e instanceof SyntaxError?"搜索服务暂时无法连接，请稍后重试。":e.message);}
      finally {if(!c.signal.aborted)setBusy(false);}
    },250);
    return()=>{clearTimeout(timer);c.abort();};
  },[query,open]);
  const choose=(value)=>{
    const code=value.trim().toUpperCase().replace(/^\$/,'').replaceAll('.','-');
    if(!/^[A-Z][A-Z0-9]{0,9}(?:-[A-Z0-9]{1,4})?$/.test(code)){setError("请选择搜索结果，或输入有效股票代码。");setOpen(true);return;}
    const next=[code,...recent.filter((v)=>v!==code)].slice(0,6);
    setRecent(next);localStorage.setItem("meridian-recent-stocks",JSON.stringify(next));
    onSelect(code);setQuery("");setOpen(false);input.current?.blur();
  };
  const submit=(e)=>{
    e.preventDefault();if(!query.trim()) {input.current?.focus();setOpen(true);return;}
    const exact=results.find((r)=>r.symbol===query.trim().toUpperCase().replace(/^\$/,'').replaceAll('.','-'));
    const selected=active>=0?results[active]:exact;
    const nameMatch=results.length===1 && results[0].english.toLowerCase().includes(query.trim().toLowerCase());
    choose(selected?.symbol || (nameMatch || /\s/.test(query)?results[0]?.symbol||query:query));
  };
  return <div className="stock-discovery" ref={root}>
    <form className="stock-search-form" onSubmit={submit}>
      <div className="stock-search-input"><Search size={18}/><input ref={input} role="combobox" aria-label="搜索美股代码或公司名称" aria-expanded={open} aria-controls="stock-search-results" aria-autocomplete="list" aria-activedescendant={active>=0?`stock-result-${active}`:undefined} value={query} maxLength={80} placeholder="输入美股代码或公司名称，例如 TSLA、AMD、Amazon" onChange={(e)=>{setQuery(e.target.value);setActive(-1);setResults([]);setOpen(true);}} onFocus={()=>setOpen(true)} onKeyDown={(e)=>{
        if(e.key==="Escape"){setOpen(false);setActive(-1);}
        if(e.key==="ArrowDown"){e.preventDefault();setOpen(true);setActive((n)=>Math.min(results.length-1,n+1));}
        if(e.key==="ArrowUp"){e.preventDefault();setActive((n)=>Math.max(-1,n-1));}
      }}/>{busy&&open&&<RefreshCw size={14} className="market-spin"/>}</div>
      <button className="button primary" type="submit">研究股票 <ArrowRight size={14}/></button>
    </form>
    {open&&<div className="stock-results-panel">
      <div className="stock-results-meta"><span>SEC 官方证券目录{meta?` · ${meta.directoryCount.toLocaleString()} 条记录`:""}</span><small>选择后核验财报与模型适用性</small></div>
      {busy&&<p role="status">正在匹配代码和公司名称…</p>}
      {error&&<p role="alert">{customerMessage(error)}</p>}
      {!busy&&!error&&!results.length&&<p role="status">未找到匹配项。请核对股票代码；也可输入完整英文公司名。</p>}
      <div id="stock-search-results" role="listbox" aria-label="股票搜索结果">{results.map((r,i)=><button type="button" role="option" aria-selected={active===i} id={`stock-result-${i}`} className={active===i?"active":""} key={r.symbol} onPointerDown={(e)=>e.preventDefault()} onClick={()=>choose(r.symbol)}><strong>{r.symbol}</strong><span>{r.name}<small>CIK {r.cik}</small></span><em>{r.exchange||"未确认交易所"}</em><ArrowRight size={13}/></button>)}</div>
      {meta?.source.stale&&<p>当前使用上次更新的公司目录，股票代码变更可能尚未收录。</p>}
    </div>}
    <div className="stock-shortcuts"><span>快捷研究</span>{featured.map(([s,n])=><button key={s} className={symbol===s?"active":""} onClick={()=>choose(s)}>{s}<small>{n}</small></button>)}</div>
    {!!recent.length&&<div className="stock-recent"><span>最近研究</span>{recent.map((s)=><button key={s} onClick={()=>choose(s)}>{s}</button>)}</div>}
    <p className="stock-coverage-note">自动识别上市公司 · 财报依据美国会计准则披露 · 特殊申报和估值口径会单独提示</p>
  </div>;
}
