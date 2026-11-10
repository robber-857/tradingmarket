import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, RefreshCw, Sparkles, Send, Newspaper, MessageSquare, ExternalLink, Clock3 } from 'lucide-react';
import './news-workspace.css';

const categories = { all: '全部', stocks: '美股', crypto: '加密货币', macro: '宏观事件' };
const labels = { official: '机构发布', media: '媒体报道', community: '社区观点' };
const kinds = { fact: '来源陈述', inference: '市场推论', hypothesis: '条件情景' };
async function jsonResponse(r) {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '请求未完成，请稍后再试。');
  return body;
}
function stamp(s, zone) { return s ? new Intl.DateTimeFormat('zh-CN', { timeZone: zone, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(s)) : '未取得'; }
function recent(item, hours) { const age = Date.now() - new Date(item.publishedAt).getTime(); return age >= -300000 && age <= hours * 3600000; }

function NewsAnalysis({ snapshot, article, onPin }) {
  const [turns, setTurns] = useState([]), [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function ask(q = '') {
    if (busy) return;
    onPin(); setBusy(true); setError('');
    const ac = new AbortController(); controller.current = ac;
    try {
      const result = await fetch('/api/news/explain', { method: 'POST', signal: ac.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot_id: snapshot.snapshotId, article_id: article?.id ?? null, question: q, conversation_id: turns.at(-1)?.conversationId ?? null }) }).then(jsonResponse);
      if (!ac.signal.aborted) { setTurns(t => [...t, result]); setQuestion(''); }
    } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
    finally { if (!ac.signal.aborted) setBusy(false); }
  }
  return <section className="news-ai-block">
    <div className="news-section-heading"><Sparkles size={17} /><h3>{article ? 'AI 简洁解读' : '今日市场重点'}</h3></div>
    {!turns.length && <><p>{article ? '简洁总结这则消息，区分来源陈述与市场推论。' : '从最近 24 小时的美股、Crypto 和宏观新闻中选取最多六则，提炼重点与可能影响。'}</p>
      <button className="button primary" disabled={busy} onClick={() => ask()}><Sparkles size={14} />{busy ? '正在分析来源…' : article ? '生成新闻解读' : '生成今日重点'}</button>
      <small>使用 RSS / 帖文预览，未读取全文。点击后生成 AI 解读。</small></>}
    <div aria-live="polite">{turns.map((turn, index) => <article className="news-answer" key={index}>
      {index > 0 && <p className="news-question">{turn.question}</p>}
      {[turn.answer.conclusion, ...turn.answer.insights].map((claim, i) => <div className={i === 0 ? 'news-takeaway' : 'news-impact'} key={i}>
        <span>{kinds[claim.kind]}</span><p>{claim.text}</p>
        <div className="news-citations">{claim.citations.filter(id => id.startsWith('S_')).map(id => <a key={id} href={turn.citations[id].sourceUrl} target="_blank" rel="noreferrer" title={turn.citations[id].display}>{turn.citations[id].label}<ArrowUpRight size={11} /></a>)}</div>
      </div>)}
      <p className="news-watch"><b>下一步验证</b>{turn.answer.watch_next}</p><p className="news-muted">{turn.answer.limitations}</p>
    </article>)}</div>
    {error && <p className="news-error" role="alert">{error}</p>}
    {!!turns.length && <><div className="news-prompts">{turns.at(-1).answer.followups.map(q => <button key={q} disabled={busy || turns.length >= 8} onClick={() => ask(q)}>{q}</button>)}</div>
      <form className="news-ask" onSubmit={e => { e.preventDefault(); if (question.trim()) ask(question); }}><input aria-label="追问新闻分析" placeholder="追问这则消息的影响…" value={question} maxLength={1200} disabled={busy || turns.length >= 8} onChange={e => setQuestion(e.target.value)} /><button className="button" type="submit" aria-label="发送新闻追问" disabled={busy || !question.trim() || turns.length >= 8}><Send size={15} /></button></form>
      {busy && <p className="news-muted" role="status">正在结合原始来源回答…</p>}
      <button className="news-reset" disabled={busy} onClick={() => { setTurns([]); setError(''); }}>开始新解读</button></>}
  </section>;
}

export default function NewsWorkspace({ timezone = 'America/New_York', initialSelection = null }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0), [tab, setTab] = useState('news'), [category, setCategory] = useState(initialSelection?.category || 'all');
  const [hours, setHours] = useState(24), [search, setSearch] = useState(''), [community, setCommunity] = useState('all');
  const [selected, setSelected] = useState(initialSelection?.article && initialSelection?.snapshot ? {article:initialSelection.article,snapshot:initialSelection.snapshot} : null), [dates, setDates] = useState([]), [day, setDay] = useState('');
  const [archive, setArchive] = useState(null), [archiveError, setArchiveError] = useState('');
  const detail = useRef(null);
  useEffect(() => {
    if (!initialSelection?.article || window.innerWidth > 1150) return;
    const timer=setTimeout(()=>detail.current?.scrollIntoView({behavior:'auto',block:'start'}),100);
    return ()=>clearTimeout(timer);
  }, []);
  useEffect(() => {
    let disposed = false, ac;
    async function load() {
      ac?.abort(); ac = new AbortController(); const current = ac;
      setBusy(true);
      try {
        const [body, editions] = await Promise.all([fetch('/api/news/feed', { signal: ac.signal }).then(jsonResponse), fetch('/api/news/editions', { signal: ac.signal }).then(jsonResponse)]);
        if (!disposed && !current.signal.aborted) { setData(body); setDates(editions.dates); setError(''); }
      } catch (e) { if (!disposed && e.name !== 'AbortError') setError(e.message); }
      finally { if (!disposed && !current.signal.aborted) setBusy(false); }
    }
    load(); const timer = setInterval(() => { if (document.visibilityState === 'visible') load(); }, 60000);
    return () => { disposed = true; ac?.abort(); clearInterval(timer); };
  }, [refresh]);
  useEffect(() => {
    setArchive(null); setArchiveError('');
    if (!day) return;
    const ac = new AbortController();
    fetch(`/api/news/editions?day=${encodeURIComponent(day)}`, { signal: ac.signal }).then(jsonResponse).then(d => { if (!ac.signal.aborted) setArchive(d); }).catch(e => { if (e.name !== 'AbortError') setArchiveError(e.message); });
    return () => ac.abort();
  }, [day]);
  function changeTab(next) { setTab(next); setSelected(null); setDay(''); setSearch(''); setCategory('all'); }
  function choose(article) {
    if (day) return;
    setSelected({ snapshot: data, article });
    if (window.innerWidth <= 1150) setTimeout(() => detail.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }), 0);
  }
  const raw = tab === 'news' ? (day ? archive?.articles || [] : data?.articles || []) : tab === 'reddit' ? (data?.reddit || []).filter(g => community === 'all' || community === g.community).flatMap(g => g.items) : data?.x || [];
  const list = raw.filter(i => (day || tab !== 'news' || recent(i, hours)) && (category === 'all' || i.categories.includes(category)) && `${i.title} ${i.excerpt} ${i.source}`.toLowerCase().includes(search.toLowerCase()));
  const context = selected || (tab === 'news' && !day && data ? { snapshot: data, article: null } : null);
  const sourceList = (data?.sources || []).filter(s => tab === 'news' ? s.kind !== 'community' : tab === 'reddit' ? s.id.startsWith('reddit-') : s.id === 'x');
  return <div className="real-news-workspace">
    <div className="real-news-top"><div className="news-mode-tabs" role="group" aria-label="热点来源">{[['news', '市场新闻'], ['reddit', 'Reddit 24 小时'], ['x', 'X 讨论样本']].map(([id, title]) => <button key={id} className={tab === id ? 'active' : ''} aria-pressed={tab === id} onClick={() => changeTab(id)}>{title}</button>)}</div>
      <button className="button" disabled={busy} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={14} className={busy ? 'news-spin' : ''} />刷新来源</button></div>
    <div className="news-live-status"><span className="news-live-dot" />{sourceList.filter(s => s.available && !s.stale).length}/{sourceList.length} 来源可用 <span>·</span> {data ? `最近检查 ${stamp(data.checkedAt, timezone)}` : '连接免费公开来源…'}<span className="news-status-note">{data?.backgroundEnabled === false ? '自动更新已关闭' : '服务可用时自动更新'}</span></div>
    <div className="real-news-controls"><div className="news-category-tabs" role="group" aria-label="新闻主题">{Object.entries(categories).map(([id, title]) => <button key={id} className={category === id ? 'active' : ''} onClick={() => setCategory(id)}>{title}</button>)}</div>
      <input aria-label="搜索市场新闻" placeholder="搜索公司、资产或关键词…" value={search} onChange={e => setSearch(e.target.value)} />
      {tab === 'news' && <><select aria-label="新闻时间范围" value={hours} disabled={!!day} onChange={e => setHours(Number(e.target.value))}><option value={24}>最近 24 小时</option><option value={168}>最近 7 天</option></select><select aria-label="每日新闻目录" value={day} onChange={e => { setDay(e.target.value); setSelected(null); }}><option value="">实时更新</option>{dates.map(d => <option value={d} key={d}>{d} 目录</option>)}</select></>}
      {tab === 'reddit' && <select aria-label="Reddit 社区" value={community} onChange={e => setCommunity(e.target.value)}><option value="all">全部关注社区</option>{data?.reddit.map(g => <option key={g.community}>{g.community}</option>)}</select>}
    </div>
    {error && <p role="alert" className="news-error">{error}{data && ' 当前保留上次结果，未确认刷新。'}</p>}
    {archiveError && <p role="alert" className="news-error">{archiveError}</p>}
    {day && <div className="news-method-note">{day} · 按悉尼日期保存的滚动 24 小时新闻目录，更新于 {stamp(archive?.updatedAt, timezone)}。归档可查看原文；AI 分析请返回实时更新。</div>}
    {tab === 'reddit' && <div className="news-method-note">保留各社区 Top(day) 的原始顺序，按发帖时间限定最近 24 小时。排名只在同一社区内可比；RSS 不提供点赞或评论数，讨论内容未经核实。</div>}
    {tab === 'x' && <div className="news-method-note">{data?.xMethod || 'X 关键词样本，非全站热榜。'}</div>}
    <div className="real-news-layout">
      <section className="real-news-list panel"><div className="news-list-heading"><h2>{tab === 'news' ? '最新市场消息' : tab === 'reddit' ? '社区热门讨论' : '金融关键词讨论'}</h2><span>{list.length} 条</span></div>
        {list.map((item, i) => <article className={`real-news-item ${context?.article?.id === item.id ? 'selected' : ''}`} key={`${item.sourceId}-${item.id}`}>
          <div className="news-item-index">{tab === 'news' ? String(i + 1).padStart(2, '0') : `#${item.rank}`}</div>
          <div className="news-item-main"><div className="news-item-meta"><strong>{item.source}</strong><span>{labels[item.kind]}</span><time dateTime={item.publishedAt}>{stamp(item.publishedAt, timezone)}</time>{item.stale && <em>缓存 · 更新失败</em>}</div>
            <h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}<ArrowUpRight size={14} /></a></h3>
            <p>{item.excerpt || '该来源只提供标题；请查看原文核实详情。'}</p>
            <div className="news-item-footer"><span>{item.categories.map(c => categories[c]).join(' / ')}</span>{item.metrics && <span>赞 {item.metrics.like_count} · 回复 {item.metrics.reply_count} · 转发 {item.metrics.retweet_count}</span>}
              {!day && <button onClick={() => choose(item)}><Sparkles size={13} />AI 解读</button>}<a href={item.url} target="_blank" rel="noreferrer">原文<ExternalLink size={11} /></a></div>
          </div>
        </article>)}
        {!list.length && <div className="news-empty"><Newspaper size={28} /><h3>{busy ? '正在读取来源…' : tab === 'x' ? 'X 数据尚未可用' : day && !archive ? '正在读取当日目录…' : '当前范围没有可用消息'}</h3><p>{tab === 'x' ? 'X 内容暂未开放。你可以先查看新闻与 Reddit 来源；这里仅展示已取得的真实内容。' : '调整主题、时间或关键词，也可以展开下方来源状态。'}</p>{tab === 'x' && <a href="https://docs.x.com/x-api/getting-started/pricing" target="_blank" rel="noreferrer">了解 X 数据访问规则<ArrowUpRight size={12} /></a>}</div>}
        <details className="news-source-details"><summary>来源状态与更新时间</summary>{sourceList.map(s => <div key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a><span>{s.error || (s.available ? '已连接' : '不可用')}{s.retrievedAt ? ` · ${stamp(s.retrievedAt, timezone)}` : ''}</span></div>)}</details>
      </section>
      <div ref={detail} className="news-detail-anchor"><aside className="news-detail panel">
        {context && !day ? <>{context.article && <div className="news-selected-story"><span>{context.article.source} · {labels[context.article.kind]}</span><h2>{context.article.title}</h2><p>{context.article.evidenceScope}</p><a href={context.article.url} target="_blank" rel="noreferrer">核对原文<ArrowUpRight size={12} /></a><small>发布 {stamp(context.article.publishedAt, timezone)} · 抓取 {stamp(context.article.retrievedAt, timezone)}</small>{context.article.stale && <p className="news-error">正在分析旧缓存，来源更新失败。</p>}</div>}
          {selected && data && data.snapshotId !== selected.snapshot.snapshotId && <button className="news-update" onClick={() => setSelected(null)}>来源已有更新，返回最新数据重新分析</button>}
          <NewsAnalysis key={`${context.snapshot.snapshotId}-${context.article?.id || 'daily'}`} snapshot={context.snapshot} article={context.article} onPin={() => setSelected(context)} />
          {context.article && tab === 'news' && <button className="news-reset" disabled={!data} onClick={() => setSelected({ snapshot: data, article: null })}>返回今日重点</button>}</> : <div className="news-read-guide"><MessageSquare size={22} /><h3>{day ? '查看历史新闻原文' : '选择一条讨论'}</h3><p>{day ? '历史目录保留来源与发布时间，实时数据和 AI 分析在“实时更新”视图中。' : '点选 AI 解读，区分社区观点、可验证事实与可能的市场影响。'}</p></div>}
        <details className="news-tools-note"><summary>热点工具与数据边界</summary><p>AIHOT 适合 AI 行业动态；last30days / last24hours 适合跨平台专题研究。技能能组织采集与总结，但不自动提供全网数据或平台权限。</p><a href="https://github.com/KKKKhazix/khazix-skills/tree/main/aihot" target="_blank" rel="noreferrer">AIHOT Skill ↗</a><a href="https://github.com/mvanhorn/last30days-skill" target="_blank" rel="noreferrer">last30days ↗</a><a href="https://github.com/jask04/last24hours-skill" target="_blank" rel="noreferrer">last24hours ↗</a></details>
      </aside></div>
    </div>
    <p className="news-bottom-note"><Clock3 size={12} />{data?.schedule || '免费公开新闻源；不保证全网覆盖或秒级更新。'} · RSS 摘要与社区帖子不等同于完整事实核验。</p>
  </div>;
}
