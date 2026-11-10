import {useEffect,useState} from 'react';
import {ArrowRight,ArrowUpRight,CalendarDays,Clock3,FileText,RefreshCw,Search,Star,Zap} from 'lucide-react';
import {readJson} from './EvidenceAnswer';
import {agenda,categoryNames,dayKey,latestReady,newsSelection,recentNews,releaseLabel,zoneNames} from './home-data';
import './home-overview.css';

const stamp=(v,zone)=>v?new Intl.DateTimeFormat('zh-CN',{timeZone:zone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'尚未取得';
const statuses={upcoming:'待公布',released:'已取得数据',pending:'等待核验','date-only':'今日 · 时间待确认'};
const kinds={fact:'来源陈述',inference:'研究判断',hypothesis:'条件情景'};
const fetchFeed=signal=>fetch('/api/news/feed',{signal}).then(readJson);
const fetchMacro=signal=>fetch('/api/macro/calendar',{signal}).then(readJson);
async function fetchBrief(signal){
  const index=await fetch('/api/briefs',{signal}).then(readJson),ready=latestReady(index);
  const edition=ready?await fetch(`/api/briefs?day=${encodeURIComponent(ready.day)}`,{signal}).then(readJson):null;
  return {index,edition};
}
function useSource(load,refresh){
  const [state,setState]=useState({data:null,loading:true,error:'',checked:null});
  useEffect(()=>{
    let disposed=false,controller,version=0;
    async function run(){
      controller?.abort();controller=new AbortController();const current=controller,token=++version;let timeout=false;
      const timer=setTimeout(()=>{timeout=true;current.abort();},45000);
      setState(s=>({...s,loading:true,error:''}));
      try{const data=await load(current.signal);if(!disposed&&token===version)setState({data,loading:false,error:'',checked:new Date().toISOString()});}
      catch(e){if(!disposed&&token===version&&(e.name!=='AbortError'||timeout))setState(s=>({...s,loading:false,error:timeout?'读取超时，请重试。':e.message}));}
      finally{clearTimeout(timer);}
    }
    run();const interval=setInterval(()=>{if(document.visibilityState==='visible')run();},60000);
    return()=>{disposed=true;controller?.abort();clearInterval(interval);};
  },[load,refresh]);
  return state;
}
function SourceState({state,name,children}){
  return <>{state.error&&<p className="home-error" role="alert">{name}：{state.error}{state.data?' 当前保留上次读取结果，未确认更新。':''}</p>}{state.loading&&!state.data?<p className="home-empty" role="status">正在读取{name}…</p>:children}</>;
}
function Citations({claim,report}){
  const refs=(claim?.citations||[]).filter(id=>id.startsWith('S_')&&report?.citations[id]?.sourceUrl);
  return <div className="home-citations">{refs.map(id=><a key={id} title={report.citations[id].display} href={report.citations[id].sourceUrl} target="_blank" rel="noreferrer">{report.citations[id].label}<ArrowUpRight size={11}/></a>)}</div>;
}
function SectionTitle({icon:Icon,title,sub,action,onClick}){
  return <div className="panel-title"><div><h2>{Icon&&<Icon size={16}/>} {title}</h2>{sub&&<p>{sub}</p>}</div>{action&&<button className="home-text-action" onClick={onClick}>{action}<ArrowUpRight size={13}/></button>}</div>;
}

export default function HomeOverview({timezone='America/New_York',watch=[],onNavigate,onNews,onEvent,onBrief,onResearch}){
  const [refresh,setRefresh]=useState(0),[category,setCategory]=useState('all');
  const news=useSource(fetchFeed,refresh),macro=useSource(fetchMacro,refresh),brief=useSource(fetchBrief,refresh);
  const now=Date.now(),zone=zoneNames[timezone]?timezone:'America/New_York';
  const report=brief.data?.edition?.payload,index=brief.data?.index;
  const today=dayKey(now,'Australia/Sydney'),isToday=report?.day===today;
  const todayRow=index?.editions.find(e=>e.day===today);
  const briefState=!brief.data?(brief.loading?'正在读取简报':'简报暂不可用'):isToday?'今日简报 · 悉尼版':report?'最近一期 · 历史简报':todayRow?.status==='generating'?'今日简报生成中':todayRow?.status==='failed'?'今日简报生成未完成':'今日简报尚未生成';
  const allNews=recentNews(news.data?.articles,'all',now),items=newsSelection(news.data?.articles,category,now);
  const schedule=agenda(macro.data?.events,now);
  const next=schedule.upcoming[0];
  const sources=(news.data?.sources||[]).filter(s=>s.kind!=='community');
  const busy=news.loading||macro.loading||brief.loading;
  const openBrief=()=>onBrief(report?.day||today);
  return <div className="home-overview">
    <div className="overview-toolbar"><div className="tabs" role="group" aria-label="首页新闻主题">{Object.entries(categoryNames).map(([id,label])=><button key={id} aria-pressed={category===id} className={category===id?'active':''} onClick={()=>setCategory(id)}>{label}</button>)}</div><div className="home-toolbar-right"><span>{dayKey(now,zone)} · {zoneNames[zone]}</span><button className="button" onClick={()=>setRefresh(v=>v+1)} disabled={busy}><RefreshCw size={14} className={busy?'home-refreshing':''}/>{busy?'读取中':'刷新首页'}</button></div></div>
    <section className="insight-banner home-summary" aria-label="每日关注摘要">
      <div className="insight-copy"><div className="eyebrow"><FileText size={14}/>{briefState}<span>DAILY FOCUS</span></div>
        <SourceState state={brief} name="简报"><h2>{report?.answer.conclusion.text||'先看事件，再核对消息与风险。'}</h2>
          <p>{report?`${report.day} 悉尼版 · 生成于 ${stamp(report.generatedAt,zone)} ${zoneNames[zone]} · ${kinds[report.answer.conclusion.kind]||'AI 研究判断'}`:'今日版就绪后，这里会显示带来源的重点结论。下方新闻与官方排期可独立查看。'}</p>
          {report&&<Citations claim={report.answer.conclusion} report={report}/>}
        </SourceState>
        <button className="insight-link" onClick={openBrief}>{report?'阅读本期完整简报':'查看每日简报'}<ArrowRight size={15}/></button>
      </div><div className="home-summary-aside"><span className="eyebrow"><CalendarDays size={13}/>下一项宏观关注</span>{next?<><strong>{next.group}</strong><p>{next.title}</p><small>{releaseLabel(next,zone)}{next.stale?' · 缓存':''}</small><button className="insight-link" onClick={()=>onEvent(next)}>核对事件<ArrowRight size={14}/></button></>:<><p>{macro.loading?'正在读取官方排期…':macro.error?'排期读取失败':'尚未取得后续排期'}</p><button className="insight-link" onClick={()=>onEvent(null)}>查看日历<ArrowRight size={14}/></button></>}</div>
    </section>
    {report&&!isToday&&<p className="home-notice">今日简报{todayRow?.status==='generating'?'正在生成':todayRow?.status==='failed'?'生成未完成':'尚未就绪'}，上方展示 {report.day} 历史版，不代表今日判断。</p>}
    <section className="market-strip home-coverage" aria-label="首页数据概况">
      {[['最近 24 小时新闻',news.data?String(allNews.length):'—',news.error?'更新失败':news.data?`${sources.filter(s=>s.available&&!s.stale).length}/${sources.length} 新闻来源可用`:'来源读取中',()=>onNews(null,null,'all')],
        ['未来 7 天宏观排期',macro.data?String(schedule.sevenDays.length):'—','同类同时间合并 · 仅已核验排期',()=>onEvent(null)],
        ['最近完成简报',report?.day?.slice(5)||'—',report?'悉尼日期 · 原始证据已保存':'等待生成 · 不补造历史',openBrief],
        ['我的关注',String(watch.length),'浏览器本地保存',()=>onNavigate('watchlist')]].map(([label,value,note,action])=><button className="market-tile" key={label} onClick={action}><span>{label}<ArrowUpRight size={12}/></span><strong>{value}</strong><small>{note}</small></button>)}
    </section>
    <div className="dashboard-grid home-primary">
      <section className="panel home-focus"><SectionTitle title={isToday?'今日研究重点':'本期研究重点'} sub={report?`${report.day} · AI 对有限来源摘要的归纳`:'读取已保存的研究结论'} action="完整简报" onClick={openBrief}/>
        <SourceState state={brief} name="简报">{report?<><div className="home-focus-list">{report.answer.insights.slice(0,3).map((claim,i)=><article key={i}><span className="home-number">0{i+1}</span><div><span className="home-kind">{kinds[claim.kind]||'研究判断'}</span><p>{claim.text}</p><Citations claim={claim} report={report}/></div></article>)}</div><div className="home-risk"><span>下一步验证</span><p>{report.answer.watch_next}</p><small>{report.answer.limitations}</small></div></>:<div className="home-empty"><FileText size={24}/><p>本期重点尚未就绪。你可以先查看右侧排期和下方最新消息。</p><button className="home-text-action" onClick={openBrief}>进入简报页<ArrowRight size={14}/></button></div>}</SourceState>
      </section>
      <section className="panel home-agenda"><SectionTitle icon={CalendarDays} title="宏观关注清单" sub="临近排期与最近待核验事件" action="日历" onClick={()=>onEvent(null)}/>
        <SourceState state={macro} name="宏观日历">{schedule.visible.length?schedule.visible.map(e=><button key={e.id} className="home-event" onClick={()=>onEvent(e)}><span className="home-event-meta"><b>{e.group}</b><span>{statuses[e.displayStatus]}</span></span><strong>{e.title}</strong><span className="home-event-time"><Clock3 size={12}/>{releaseLabel(e,zone)}</span><small>前值 {e.previous?.display||'未提供'} · 预期 {e.forecast?.display||'暂无预期'}</small>{e.displayStatus==='released'&&<small>实际 {e.actual?.display||'尚未取得'}</small>}<span className="home-event-source">{e.source}{e.stale?' · 更新失败，缓存':''}<ArrowRight size={13}/></span></button>):<p className="home-empty">当前未取得可展示的近期排期。请在宏观日历核对来源覆盖；不代表近期没有重要事件。</p>}
        </SourceState><p className="home-footnote">免费官方来源通常不提供市场一致预期。缺失时保留空值。</p>
      </section>
    </div>
    <div className="dashboard-grid home-secondary">
      <section className="panel home-news"><SectionTitle icon={Zap} title="最新市场热点" sub={`最近 24 小时 · ${categoryNames[category]} · 按时间选取，全部视图兼顾主题`} action="全部热点" onClick={()=>onNews(null,null,category)}/>
        <SourceState state={news} name="市场新闻">{items.length?<div>{items.map((a,i)=><article key={a.id} className="home-news-row"><span className="home-number">{String(i+1).padStart(2,'0')}</span><div><div className="home-news-meta"><span>{a.kind==='official'?'机构发布':'媒体报道'} · {a.source}</span><time>{stamp(a.publishedAt,zone)} {zoneNames[zone]}</time></div><button className="home-news-title" onClick={()=>onNews(a,news.data,category)}>{a.title}<ArrowUpRight size={14}/></button><p>{a.excerpt||'来源未提供摘要，请核对原文。'}</p><div className="home-news-bottom"><span>{a.categories.map(k=>categoryNames[k]).filter(Boolean).join(' / ')}{a.stale?' · 更新失败，缓存':''}</span><a href={a.url} target="_blank" rel="noreferrer">原文 ↗</a></div></div></article>)}</div>:<p className="home-empty">当前主题没有最近二十四小时的可用新闻。可切换主题或查看来源状态。</p>}</SourceState>
      </section>
      <aside className="panel home-research"><SectionTitle icon={Star} title="继续你的研究" sub="从关注资产进入，核对数据与假设" action="管理" onClick={()=>onNavigate('watchlist')}/>
        {watch.length?watch.slice(0,6).map(symbol=><div className="home-watch-row" key={symbol}><strong>{symbol}</strong>{['BTC','ETH'].includes(symbol)?<button onClick={()=>onNews(null,null,'crypto')}>加密市场热点<ArrowUpRight size={12}/></button>:<div>{[['financials','财报'],['fundamentals','基本面'],['options','期权']].map(([dest,label])=><button key={dest} onClick={()=>onResearch(symbol,dest)}>{label}<ArrowUpRight size={11}/></button>)}</div>}</div>):<p className="home-empty">还没有关注资产。先添加想持续研究的股票或币种。</p>}
        <button className="button home-find" onClick={()=>onNavigate('financials')}><Search size={14}/>搜索其他股票</button><div className="home-scope"><b>每个结论，都回到证据</b><p>财报看来源，估值看假设，期权看成本与风险。此处不展示未经接入的资产报价。</p></div>
      </aside>
    </div>
    <details className="home-source-details"><summary>数据来源与更新状态</summary><div className="home-source-grid">{[['新闻',news],['宏观',macro],['简报',brief]].map(([label,state])=><div key={label}><b>{label}</b><span>{state.loading?'正在检查':state.error?'更新失败':state.data?'已读取':'未取得'}</span><small>最近成功读取 {stamp(state.checked,zone)} {zoneNames[zone]}</small></div>)}</div>
      {sources.map(s=><p key={s.id}>{s.name}：{s.stale?'源站更新失败 · 使用缓存':s.available?'可用':'不可用'} · 采集 {stamp(s.retrievedAt,zone)} {zoneNames[zone]}</p>)}
      {macro.data?.warnings?.map((w,i)=><p key={i}>{w}</p>)}
      <p>简报按悉尼日期分版，首页只读取已生成版本，不自动调用 AI。新闻为 RSS 标题与摘要；首页不展示模拟行情、情绪指数或收益预测。采集时间不等于发布时间；可用来源也不保证完整覆盖。</p>
    </details>
  </div>;
}
