import {useEffect,useState} from 'react';
import {Plus,RefreshCw,X} from 'lucide-react';
import {readJson} from './EvidenceAnswer';
import './watchlist.css';

const number=n=>n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
function Trend({item}) {
  const points=(item?.history||[]).filter(p=>Number.isFinite(p.value));
  if(points.length<2)return <span className="muted">走势暂不可用</span>;
  const values=points.map(p=>p.value),min=Math.min(...values),range=Math.max(...values)-min;
  return <svg className="sparkline" viewBox="0 0 120 40" role="img" aria-label={`${item.watchSymbol}近一个月日线走势`}><polyline fill="none" stroke={values.at(-1)>=values[0]?'var(--success)':'var(--danger)'} strokeWidth="2" points={values.map((v,i)=>`${2+i/(values.length-1)*116},${36-(v-min)/(range||1)*32}`).join(' ')}/></svg>;
}

export default function Watchlist({watch,assets,onAdd,onOpen,onRemove,timezone}) {
  const [quotes,setQuotes]=useState({}),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const symbols=watch.join(',');
  useEffect(()=>{
    let disposed=false,busy=false,controller;
    async function load(){
      if(busy)return;
      busy=true;setLoading(true);controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),120000);
      try {
        const list=symbols.split(',').filter(Boolean),items=[];
        for(let i=0;i<list.length;i+=50){
          const data=await fetch(`/api/market/watchlist?symbols=${encodeURIComponent(list.slice(i,i+50).join(','))}`,{signal:controller.signal}).then(readJson);
          items.push(...data.items);
        }
        if(!disposed){setQuotes(Object.fromEntries(items.map(item=>[item.watchSymbol,item])));setError('');}
      } catch {if(!disposed)setError('行情更新失败，请重试；已有报价为上次取得的数据。');}
      finally{clearTimeout(timeout);busy=false;if(!disposed)setLoading(false);}
    }
    load();const timer=setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
    return()=>{disposed=true;controller?.abort();clearInterval(timer);};
  },[symbols,refresh]);
  const stamp=value=>new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
  return <section className="panel watchlist-panel">
    <div className="panel-title"><div><h2>我的研究清单</h2><p>{watch.length} 个关注资产 · 保存在当前浏览器</p></div><div style={{display:'flex',gap:12}}><button className="button" disabled={loading} onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={14}/>{loading?'读取中':'刷新行情'}</button><button className="button" onClick={onAdd}>添加资产<Plus size={14}/></button></div></div>
    {error&&<p role="alert" className="home-error">{error}</p>}
    {watch.length?<div className="table-wrap"><table className="watch-table"><thead><tr><th>资产</th><th>参考价格</th><th>涨跌幅</th><th>近一个月走势</th><th>删除</th></tr></thead><tbody>{watch.map(symbol=>{
      const asset=assets.find(a=>a.symbol===symbol)||{symbol,name:'已关注美股',type:'美股',color:'var(--surface-selected)'},q=quotes[symbol];
      const available=q?.available&&Number.isFinite(q.price),change=available&&Number.isFinite(q.changePct)?q.changePct:null;
      return <tr key={symbol}><td><button className="asset-table-name" onClick={()=>onOpen(asset)}><span className="asset-logo" style={{background:asset.color}}>{symbol[0]}</span><span><b>{symbol}</b><small>{asset.name}</small></span></button></td>
        <td>{available?number(q.price):'—'} <small>{q?.unit||(['SPX','NDX'].includes(symbol)?'点':'USD')}</small><div className="fine-print">{q?.asOf?stamp(q.asOf):loading?'正在读取…':'暂无行情'}</div>{available&&<div className="fine-print">{error||q.stale?'更新失败 · 上次报价':q.quoteOld?'较早报价':'参考行情 · 可能延迟'}</div>}{q&&<div className="fine-print"><a href={q.sourceUrl} target="_blank" rel="noreferrer">{q.source} ↗</a></div>}</td>
        <td className={error||q?.stale||change===null?'muted':change>0?'up':change<0?'down':'muted'}>{change===null?'—':`${change>0?'+':''}${number(change)}%`}</td>
        <td><Trend item={q}/></td>
        <td><button className="icon-button" aria-label={`删除关注 ${symbol}`} title={`删除关注 ${symbol}`} onClick={()=>onRemove(symbol)}><X size={17}/></button></td></tr>;
    })}</tbody></table></div>:<div className="empty-state"><h3>从一个资产开始研究</h3><p>搜索资产，然后加入关注清单。</p><button className="button primary" onClick={onAdd}>添加资产<Plus size={16}/></button></div>}
    <p className="fine-print" style={{marginTop:20}}>来源：Yahoo Finance · 页面可见时每 5 分钟检查，服务端缓存最长 5 分钟 · 报价时间：{timezone}。涨跌幅相对前一交易日收盘，BTC / ETH 相对前一 UTC 日收盘；走势为近一个月日线。缺失数据保留为空。</p>
  </section>;
}
