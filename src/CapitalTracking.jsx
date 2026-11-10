import {useEffect,useState} from 'react';
import {ArrowUpRight,ChevronLeft,ChevronRight,FileText,RefreshCw,Search,Landmark,Users,Clock3} from 'lucide-react';
import './capital-tracking.css';

const changes={new:'新增披露',increase:'数量增加',decrease:'数量减少',removed:'不再披露',unchanged:'数量不变',unknown:'未比较'};
const actions={purchase:'买入',sale:'卖出',exchange:'交换',holding:'年度资产',other:'其他'};
const owners={self:'本人',spouse:'配偶',joint:'共同',dependent:'受抚养人',undisclosed:'未单列归属'};
const integer=value=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:0}).format(value);
const usd=value=>value==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:2}).format(value);
const stamp=value=>value?new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)):'尚未检查';
async function get(url,signal){const response=await fetch(url,{signal,cache:'no-store'});const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'公开披露暂时无法读取，请重试。');return body;}
function SourceLink({href,children}){return <a href={href} target="_blank" rel="noreferrer">{children}<ArrowUpRight size={13}/></a>;}

export default function CapitalTracking(){
  const [profiles,setProfiles]=useState([]),[selected,setSelected]=useState('berkshire'),[group,setGroup]=useState('all');
  const [result,setData]=useState(null),[busy,setBusy]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
  // A selection renders before its loading effect runs. Never render another
  // profile's rows with the newly selected profile's table schema.
  const data=result?.profile?.id===selected?result:null;
  const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[category,setCategory]=useState('all'),[offset,setOffset]=useState(0);
  useEffect(()=>{const ac=new AbortController();get('/api/capital/profiles',ac.signal).then(x=>setProfiles(x.profiles)).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>ac.abort();},[revision]);
  useEffect(()=>{const timer=setTimeout(()=>{setSearch(query);setOffset(0);},250);return()=>clearTimeout(timer);},[query]);
  useEffect(()=>{
    const ac=new AbortController();setBusy(true);setError('');setData(null);
    get('/api/capital/'+selected+'?'+new URLSearchParams({q:search,category,offset:String(offset),limit:'25'}),ac.signal)
      .then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!ac.signal.aborted)setBusy(false);});
    return()=>ac.abort();
  },[selected,search,category,offset,revision]);
  function choose(id){if(id!==selected){setData(null);setBusy(true);}setSelected(id);setQuery('');setSearch('');setCategory('all');setOffset(0);}
  function chooseGroup(value){setGroup(value);if(value!=='all'&&profiles.find(p=>p.id===selected)?.kind!==value){const first=profiles.find(p=>p.kind===value);if(first)choose(first.id);}}
  const profile=profiles.find(p=>p.id===selected)||data?.profile;
  const institution=profile?.kind==='institution';
  const filtered=profiles.filter(p=>group==='all'||p.kind===group);
  const primary=data?.documents?.find(d=>!institution||d.period===data.reportDate);
  return <div className="capital-workspace">
    <div className="capital-toolbar"><div className="capital-segments" role="group" aria-label="跟踪对象类型">{[['all','全部对象'],['institution','机构'],['person','公众人物']].map(([id,label])=><button key={id} aria-pressed={group===id} onClick={()=>chooseGroup(id)}>{label}</button>)}</div><span><Clock3 size={13}/>按披露更新 · 每 6 小时检查</span></div>
    <div className="capital-layout">
      <aside className="capital-directory" aria-label="选择跟踪对象"><p className="capital-overline">公开披露观察名单 <span>{filtered.length}</span></p><div className="capital-people">{filtered.map(p=><button className={selected===p.id?'is-selected':''} key={p.id} onClick={()=>choose(p.id)} aria-pressed={selected===p.id}><span className="capital-monogram">{p.initials}</span><span className="capital-person-name"><strong>{p.name}</strong><small>{p.english}</small><span>{p.kind==='institution'?'SEC · 13F 季报':'个人 / 家庭披露'}</span></span><ChevronRight size={14}/></button>)}</div><div className="capital-directory-note"><FileText size={17}/><p>从原始披露出发<small>报告存在披露延迟。这里展示公开记录，不是实时账户，也不推算跟单收益。</small></p></div></aside>
      <section className="capital-detail" aria-busy={busy} aria-label="披露详情">
        <header className="capital-profile-heading"><div><span className="capital-overline">{institution?<Landmark size={14}/>:<Users size={14}/>} {institution?'INSTITUTIONAL FILINGS':'PUBLIC FINANCIAL DISCLOSURES'}</span><h2>{profile?.name||'大资金动向'}</h2><p>{profile?.scope}</p></div><button className="button capital-refresh" onClick={()=>setRevision(r=>r+1)} disabled={busy}><RefreshCw size={14} className={busy?'is-spinning':''}/>{busy?'读取中':'检查更新'}</button></header>
        <div className="capital-metrics"><div><span>{institution?'报告期末':'最新报告日期'}</span><strong>{(institution?data?.reportDate:data?.latestDisclosure)||'—'}</strong><small>{institution?'季度末的申报快照':'非交易发生日期'}</small></div><div><span>{institution?'申报证券市值':'已提取明细'}</span><strong>{institution?usd(data?.totalValue):data?.recordCount==null?'—':integer(data.recordCount)}</strong><small>{institution?'USD · 不等于管理总资产':'最新报告中的部分记录'}</small></div><div><span>{institution?'本期证券条目':'报告类型'}</span><strong>{institution?data?.holdingsCount==null?'—':integer(data.holdingsCount):primary?.type==='Annual'?'年度披露':primary?'交易报告':'—'}</strong><small>{institution?'同类别与期权方向合并':'保留金额区间与家庭归属'}</small></div></div>
        {error&&<div className="capital-alert" role="alert">{error}<button className="button" onClick={()=>setRevision(r=>r+1)}>重新读取</button></div>}
        {data?.error&&<p className="capital-alert" role="status">{data.error}</p>}
        <div className="capital-table-heading"><div><h3>{institution?'披露持仓与季度变化':'最新报告明细'}</h3><p>{institution?(data?.previousReportDate?'数量对比 '+data.previousReportDate+' · 包括本期不再披露的条目':'与上一报告期比较申报数量'):'年度资产与交易分开展示，均保留原文页码。'}</p></div><label className="capital-search"><Search size={15}/><input aria-label="搜索披露证券" value={query} onChange={e=>setQuery(e.target.value)} placeholder={institution?'搜索名称 / CUSIP':'搜索资产 / 股票代码'}/></label></div>
        <div className="capital-filters" role="group" aria-label="明细筛选">{(institution?[['all','全部'],['new','新增披露'],['increase','数量增加'],['decrease','数量减少'],['removed','不再披露']]:[['all','全部'],['holding','年度资产'],['purchase','买入'],['sale','卖出'],['exchange','交换']]).map(([id,label])=><button key={id} aria-pressed={category===id} onClick={()=>{setCategory(id);setOffset(0);}}>{label}</button>)}</div>
        {busy?<div className="capital-loading" role="status"><RefreshCw size={22} className="is-spinning"/><strong>正在读取公开披露</strong><p>首次同步需下载原始报告；个人扫描文件提取可能需要约两分钟。</p></div>:data?.rows?.length?<><div className="capital-table-scroll"><table className="capital-table"><caption className="capital-sr-only">{profile?.name}公开披露明细</caption><thead><tr>{(institution?['证券 / 类别','申报市值 · USD','占本期表内市值','申报数量','季度变化']:['披露资产','记录性质','交易日期','申报金额 · USD','归属 / 来源']).map(label=><th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{data.rows.map(row=><tr key={row.id}><td><strong>{row.name}</strong><small>{institution?`${row.cusip} · ${row.class}${row.option?' · '+row.option:''}`:row.ticker||'原文未列股票代码'}</small>{!institution&&row.note&&<details className="capital-row-note"><summary>披露备注</summary><p>{row.note}</p></details>}</td>{institution?<><td className="capital-numeric">{usd(row.value)}</td><td className="capital-numeric"><span className="capital-weight">{row.weight.toFixed(2)}%<span style={{width:Math.min(100,row.weight*2)+'%'}}/></span></td><td className="capital-numeric">{integer(row.shares)}<small>{row.unit==='SH'?'股 / 份':'本金单位'}</small></td><td><span className={'capital-change '+row.change}>{changes[row.change]}</span><small>{row.shareChangePct==null?(row.shareChange==null?'—':(row.shareChange>0?'+':'')+integer(row.shareChange)):(row.shareChangePct>0?'+':'')+row.shareChangePct.toFixed(2)+'%'}</small></td></>:<><td><span className={'capital-change '+row.action}>{actions[row.action]}</span><small>{row.recordType==='holding'?'报告中的资产区间':'交易记录'}</small></td><td className="capital-numeric">{row.date||'不适用'}<small>报告：{row.disclosureDate}</small></td><td className="capital-amount-range">{row.amount}</td><td><span>{owners[row.owner]}</span><SourceLink href={row.sourceUrl}>原文第 {row.page} 页</SourceLink></td></>}</tr>)}</tbody></table></div><div className="capital-pagination"><span>第 {offset+1}–{Math.min(offset+data.limit,data.filteredCount)} 条，共 {integer(data.filteredCount)} 条</span><div><button className="icon-button" aria-label="上一页" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}><ChevronLeft size={17}/></button><button className="icon-button" aria-label="下一页" disabled={offset+25>=data.filteredCount} onClick={()=>setOffset(offset+25)}><ChevronRight size={17}/></button></div></div></>:!error&&<div className="capital-empty"><FileText size={26}/><h3>{query||category!=='all'?'没有匹配的披露记录':'暂无可展示的结构化明细'}</h3><p>{query||category!=='all'?'试试其他名称，或清除筛选。':'已取得的原始报告会列在下方。未取得的数据不会显示成零持仓。'}</p>{(query||category!=='all')&&<button className="button" onClick={()=>{setQuery('');setSearch('');setCategory('all');setOffset(0);}}>清除筛选</button>}</div>}
        {data&&<footer className="capital-provenance"><div><span className={'capital-status '+(data.stale?'is-stale':'')}/><strong>{data.stale?'更新未完成':'公开来源'}</strong><span>成功检查：{stamp(data.checkedAt)}</span><span>{data.extraction}</span></div><p>{data.coverage}</p><p>{data.notice}</p>{institution&&data.latestDisclosure&&<p>本期最新申报：{data.latestDisclosure}。证券市值按报告时点计算；期权行的标的数量不等于期权合约数。</p>}<small>在页面访问时按 6 小时缓存检查；“检查更新”不会绕过缓存。{data.discoveryUrl&&<SourceLink href={data.discoveryUrl}>查看披露目录</SourceLink>}</small></footer>}
        {!!data?.documents?.length&&<section className="capital-documents"><h3><FileText size={16}/>原始披露文件</h3><div>{data.documents.map(doc=><article key={doc.id}><div><span>{doc.source} · {doc.type}</span><strong>{doc.date}</strong><small>{doc.period?'报告期 '+doc.period:doc.title}</small></div><SourceLink href={doc.url}>查看原文</SourceLink></article>)}</div></section>}
      </section>
    </div>
  </div>;
}
