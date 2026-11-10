import {customerMessage} from './customer-message';
import {dayKey, sevenDayEvents} from "./home-data";
import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Clock3, RefreshCw, Sparkles, Send, CalendarDays } from 'lucide-react';
import './macro-calendar.css';
import FieldHelp from './FieldHelp';

const descriptions = {
  release: '这项数据对外公布的日期和时间，按当前选择的时区显示；标记为暂定或时刻待确认时，请以官方日程为准。它不是数据所统计的月份。',
  period: '数据反映的月份或季度，不是公布时间。例如：11 月公布 10 月 CPI，统计所属期就是 10 月；环比比较 10 月与 9 月，同比比较当年 10 月与去年 10 月。',
  previous: '上一统计期的数值；利率决议通常指上次决议的利率。历史数据可能修订，具体版本以页面的数据来源与口径为准。',
  forecast: '此处数值为公开来源转引的调查预期，不代表本站汇总的全市场共识。各家机构与模型预测在下方分开展示。暂无预期或横线表示没有取得可用预期，不代表零。',
  actual: '已取得的本期公布结果。待公布表示尚未到公布时间；尚未取得表示系统还没有取得可用数值，不代表零。',
  surprise: '本期实际值减去公开预期参考，只有两者口径可比时才计算。正值表示高于预期，负值表示低于预期；不能直接等同于市场利好或利空。',
};
const Help = ({ field, label }) => <FieldHelp label={label}>{descriptions[field]}</FieldHelp>;

const groups = { ALL: '全部', CPI: 'CPI 通胀', NFP: '非农就业', PCE: 'PCE 物价', FOMC: 'FOMC 决议' };
const states = { upcoming: '待公布', released: '已取得数据', pending: '等待核验' };
const kinds = { fact: '数据事实', inference: '分析推论', hypothesis: '条件情景' };
const zones = { 'America/New_York': '美东时间', 'Asia/Shanghai': '北京时间', 'Australia/Sydney': '悉尼时间' };

function time(value, zone, dateOnly = false) {
  if (!value) return '发布日期未核验';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: zone, month: '2-digit', day: '2-digit',
    ...(!dateOnly && { hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short' }) }).format(new Date(value));
}
function releaseTime(e, zone) {
  if (e.timePrecision === 'date-only') return `${time(e.releaseAt, 'America/New_York', true)} 美东 · 时刻待确认`;
  return time(e.releaseAt, zone) + (e.timePrecision === 'estimated' ? '（暂定）' : '');
}
function value(m, fallback = '未提供') { return m?.display ?? fallback; }

async function jsonResponse(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '请求未完成，请稍后重试。');
  return body;
}

function MacroExplanation({ event }) {
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function ask(q = '') {
    if (busy) return;
    const ac = new AbortController(); controller.current = ac;
    setBusy(true); setError('');
    try {
      const result = await fetch('/api/macro/explain', { method: 'POST', signal: ac.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ snapshot_id: event.snapshotId,
          question: q, conversation_id: turns.at(-1)?.conversationId ?? null }) }).then(jsonResponse);
      if (!ac.signal.aborted) { setTurns(t => [...t, result]); setQuestion(''); }
    } catch (err) { if (err.name !== 'AbortError') setError(err.message); }
    finally { if (!ac.signal.aborted) setBusy(false); }
  }
  return <section className="macro-ai">
    <div className="macro-section-title"><Sparkles size={18} /><h3>AI 跨资产解读</h3><span>{event.actual ? '数据解读' : event.status === 'upcoming' ? '发布前情景' : '数据待核验'}</span></div>
    {!turns.length && <><p>结合各家机构的预测区间与分歧，分析实际值高于、低于或落在区间内时，对美股和加密的可能影响。数据事实、分析推论与条件情景分别标注，引用本次研究所用数据。</p>
      <button className="button primary" onClick={() => ask()} disabled={busy}><Sparkles size={15} />{busy ? '正在分析…' : '分析对美股与 Crypto 的影响'}</button></>}
    <div className="macro-conversation" aria-live="polite">
      {turns.map((turn, index) => <article className="macro-answer" key={index}>
        {index > 0 && <div className="macro-question">{turn.question}</div>}
        {[turn.answer.conclusion, ...turn.answer.insights].map((claim, i) => <div className={i === 0 ? 'macro-conclusion' : 'macro-insight'} key={i}>
          <span className="macro-kind">{kinds[claim.kind]}</span><p>{claim.text}</p>
          <div className="macro-citations">{claim.citations.flatMap(id => {
            const citation=turn.citations[id];
            return (citation.sources || [citation]).map((source,j)=><a key={`${id}-${j}`} href={source.sourceUrl} target="_blank" rel="noreferrer"
              title={`${citation.label}：${citation.display} · 来源更新 ${source.sourceUpdatedAt || '见原文'} · 收录 ${source.retrievedAt || turn.generatedAt}`}>{citation.label}{source.source ? ` · ${source.source}` : ''}<ArrowUpRight size={11} /></a>);
          })}</div>
        </div>)}
        <p className="macro-watch"><b>继续观察</b>{turn.answer.watch_next}</p>
        <p className="macro-muted">{turn.answer.limitations}</p>
      </article>)}
    </div>
    {error && <p role="alert" className="macro-error">{customerMessage(error)}</p>}
    {turns.length > 0 && <>
      <div className="macro-prompts">{turns.at(-1).answer.followups.map(q => <button key={q} disabled={busy || turns.length >= 8} onClick={() => ask(q)}>{q}</button>)}</div>
      <form className="macro-ask" onSubmit={e => { e.preventDefault(); if (question.trim()) ask(question); }}>
        <input aria-label="追问宏观分析" placeholder="追问这次事件的影响…" maxLength={1200} value={question} onChange={e => setQuestion(e.target.value)} disabled={busy || turns.length >= 8} />
        <button className="button" type="submit" disabled={busy || !question.trim() || turns.length >= 8} aria-label="发送追问"><Send size={16} /></button>
      </form>
      {busy && <p role="status" className="macro-muted">正在结合当前事件证据分析…</p>}
      <button className="macro-reset" disabled={busy} onClick={() => { setTurns([]); setError(''); }}>开始新解读</button>
    </>}
  </section>;
}

function ForecastDate({ row, zone }) {
  return <>{row.sourceUpdatedTimestamp ? new Intl.DateTimeFormat('zh-CN', {timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', timeZoneName: 'short', hour12: false}).format(new Date(row.sourceUpdatedTimestamp)) : `${row.sourceUpdatedAt}（原文仅提供日期）`}</>;
}

const translationRequests = new Map();
function InstitutionExcerpt({ row, snapshotId, zone }) {
  const [language, setLanguage] = useState('zh');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const key = row.institutionView.excerpt;
    setError('');
    if (!translationRequests.has(key)) {
      const request = fetch('/api/macro/institution-translation', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({snapshot_id:snapshotId,record_id:row.id})}).then(jsonResponse);
      translationRequests.set(key, request);
      request.catch(() => translationRequests.delete(key));
    }
    translationRequests.get(key).then(value => {if(active)setResult(value);}).catch(err => {if(active)setError(err.message);});
    return () => { active = false; };
  }, [row.id, snapshotId, attempt]);
  return <>
    <div className="macro-language-toggle" role="group" aria-label={`${row.source}观点语言`}>
      <button aria-pressed={language==='zh'} onClick={()=>setLanguage('zh')}>中文 · AI 翻译</button>
      <button aria-pressed={language==='en'} onClick={()=>setLanguage('en')}>英文原文</button>
    </div>
    {language==='en' ? <blockquote lang="en">{row.institutionView.excerpt}</blockquote>
      : result ? <><span className="macro-kind">AI 翻译 · 机构原文节选</span><blockquote lang="zh-CN">{result.text}</blockquote>
        <p className="macro-muted">仅翻译原文，不是 AI 市场推论；以英文原文为准。译于 {time(result.translatedAt, zone)}</p></>
      : error ? <><p className="macro-warning" role="status">{customerMessage(error)}</p><blockquote lang="en">{row.institutionView.excerpt}</blockquote><button className="button" onClick={()=>setAttempt(a=>a+1)}>重试中文翻译</button></>
      : <p className="macro-muted" role="status">正在翻译机构原文… 可切换英文查看。</p>}
  </>;
}

function InstitutionComparison({ event, rows, zone }) {
  const comparison = event.institutionComparison;
  const sorted = [...rows].sort((a,b) => Number(a.stale)-Number(b.stale) || a.metric.value-b.metric.value || a.source.localeCompare(b.source));
  const difference = row => {
    if (row.stale || !event.forecast || event.forecast.value == null || event.forecast.unit !== row.metric.unit) return '—';
    const n = Number((row.metric.value-event.forecast.value).toFixed(8));
    return `${n > 0 ? '+' : ''}${n.toLocaleString('zh-CN', {maximumFractionDigits: 8})} ${row.metric.unit === '%' ? '百分点' : '人'}`;
  };
  return <>
    {comparison ? <div className="macro-bank-summary">
      <strong>已收录 {comparison.count} 家 · 预测范围 {comparison.min.display} – {comparison.max.display}</strong>
      <p>中位数 {comparison.median.display} · 最高与最低相差 {comparison.spread.value.toLocaleString('zh-CN', {maximumFractionDigits: 8})} {comparison.spread.unit}</p>
      <p>来源日期 {comparison.earliestUpdate} 至 {comparison.latestUpdate}。仅反映已收录样本，更新时间不同，不代表全市场共识。</p>
    </div> : <p className="macro-muted">当前可比机构不足两家，暂不计算分歧范围。</p>}
    <div className="macro-bank-table-wrap"><table className="macro-bank-table" aria-label="机构预测对比">
      <thead><tr><th>机构 / 来源更新</th><th>预测</th><th>与调查预期差</th></tr></thead>
      <tbody>{sorted.map(row => <tr key={row.id} className={row.stale ? 'macro-bank-stale' : ''}>
        <td><a href={row.sourceUrl} target="_blank" rel="noreferrer">{row.source}<ArrowUpRight size={11} /></a>
          <small><ForecastDate row={row} zone={zone} /></small>
          <small>收录 {time(row.retrievedAt, zone)}{row.collectedAfterRelease ? ' · 公布后收录' : ''}</small>
          {row.stale && <small>旧记录，不纳入比较</small>}</td>
        <td>{row.metric.display}</td><td>{difference(row)}</td>
      </tr>)}</tbody>
    </table></div>
    <div className="macro-institution-views" aria-label="机构原文观点">
      <h4>机构原文观点</h4>
      <p className="macro-muted">默认展示机构原文节选的 AI 中文翻译，可切换英文原文。翻译不补写理由，也不代表下方 AI 的市场推论；完整判断与限定条件请阅读原文。</p>
      {sorted.map(row => <article className="macro-source-view" key={row.id}>
        <div><strong>{row.source}</strong><span className="macro-kind">{row.institutionView ? '机构原文观点' : '仅数值预测'}</span></div>
        {row.institutionView ? <>
          <InstitutionExcerpt key={row.id} row={row} snapshotId={event.snapshotId} zone={zone} />
          <p className="macro-muted">发布：{time(row.institutionView.publishedAt, zone)} · 更新：<ForecastDate row={row} zone={zone} /></p>
          <p className="macro-muted">原文收录：{time(row.institutionView.collectedAt, zone)}{row.collectedAfterRelease ? ' · 公布后收录，不代表当时系统已知' : ''}</p>
        </> : <p className="macro-muted">目前仅收录数值预测，未取得可展示的原文观点或判断依据。不会用 AI 推论代替机构原话。</p>}
        {row.stale && <p className="macro-warning">旧记录，仅供历史参考，未纳入当前分歧统计。</p>}
        <a href={row.sourceUrl} target="_blank" rel="noreferrer">阅读机构原文与完整上下文<ArrowUpRight size={12}/></a>
      </article>)}
    </div>
  </>;
}

function PublicForecasts({ event, zone }) {
  const rows = event.publicForecasts || [];
  return <section className="macro-public-forecasts" aria-label="公开预期参考">
    <h3>公开预期参考<Help field="forecast" label="预测来源" /></h3>
    <p className="macro-muted">按本事件统计期与指标口径匹配。机构样本、调查预期和模型分别展示，不能混合为全市场共识。</p>
    {Object.entries({ consensus: '市场调查预期', institution: '机构观点与分歧', model: '模型预测' }).map(([kind, label]) => <div className="macro-forecast-group" key={kind}>
      <h4>{label}</h4>
      {kind === 'institution' && rows.some(r => r.kind === kind)
        ? <InstitutionComparison event={event} rows={rows.filter(r => r.kind === kind)} zone={zone} />
        : rows.filter(r => r.kind === kind).length ? rows.filter(r => r.kind === kind).map(r => <article key={r.id} className="macro-forecast-row">
        <div><a href={r.sourceUrl} target="_blank" rel="noreferrer">{r.source}<ArrowUpRight size={12} /></a><strong>{r.metric.display}</strong></div>
        <p>来源更新：<ForecastDate row={r} zone={zone} /> · 所属期：{r.reference}</p>
        <p>收录：{time(r.retrievedAt, zone)}{r.collectedAfterRelease ? ' · 公布后收录，不代表公布前已知信息' : ''}</p>
        {r.stale && <p className="macro-warning">旧记录：来源检查失败或预测超过有效期，仅供参考。</p>}
      </article>) : <p className="macro-muted">本期暂无已核验的{label}。</p>}
    </div>)}
  </section>;
}

function EventDetail({ event, zone, updated, onUpdate }) {
  return <aside className="macro-detail panel" aria-label="事件详情">
    <div className="macro-detail-top"><span>{event.group} / 美国</span><span>{states[event.status]}</span></div>
    <h2>{event.title}</h2>
    <p className="macro-event-time"><CalendarDays size={15} />{releaseTime(event, zone)}<Help field="release" label="发布时间" /></p>
    <p className="macro-muted">统计所属期<Help field="period" label="统计所属期" />：{event.reference || '未提供'}</p>
    {updated && <button className="macro-update" onClick={onUpdate}>已取得更新的数据，使用最新数据重新分析</button>}
    {event.stale && <p className="macro-warning">来源暂未更新，当前保留上次数据。请核对数据时间。</p>}
    <dl className="macro-values">
      <div><dt>前值<Help field="previous" label="前值" /></dt><dd>{value(event.previous)}</dd></div>
      <div><dt>公开预期参考<Help field="forecast" label="公开预期参考" /></dt><dd>{value(event.forecast, '暂无预期')}</dd></div>
      <div><dt>实际值<Help field="actual" label="实际值" /></dt><dd>{value(event.actual, event.status === 'upcoming' ? '待公布' : '尚未取得')}</dd></div>
    </dl>
    {event.forecastSource && <p className="macro-muted">预期来源：{event.forecastSource}{event.forecastUpdatedAt && ` · 来源更新 ${event.forecastUpdatedAt}`}</p>}
    {event.previousBeforeRevision && <p className="macro-muted">前值修订：{value(event.previousBeforeRevision)} → {value(event.previous)}（以来源最新提供的数据为准）</p>}
    <div className="macro-surprise"><span>实际 − 预期<Help field="surprise" label="实际与预期差" /></span><strong>{event.surprise?.display ?? '暂无可比预期差'}</strong></div>
    <p className="macro-muted">{event.valueBasis}</p>
    {event.forecastCollectedAfterRelease && <p className="macro-muted">调查预期为公布后补收录；与当前实际值的差不代表历史首发意外程度。</p>}
    {event.group !== 'FOMC' && <PublicForecasts event={event} zone={zone} />}
    <details className="macro-provenance"><summary>数据来源与口径</summary>
      <p>{event.note}</p>
      <a href={event.sourceUrl} target="_blank" rel="noreferrer">{event.source}<ArrowUpRight size={12} /></a>
      {event.releaseSourceUrl && <a href={event.releaseSourceUrl} target="_blank" rel="noreferrer">官方发布时间原文<ArrowUpRight size={12} /></a>}
      {event.previousSourceUrl && <a href={event.previousSourceUrl} target="_blank" rel="noreferrer">前次利率决议<ArrowUpRight size={12} /></a>}
      <p>获取时间：{new Intl.DateTimeFormat('zh-CN', { timeZone: zone, dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.retrievedAt))}</p>
      <p>预期来源：{event.forecast ? event.forecastSource : '本期暂无已核验的市场调查预期'}</p>
      {event.providerUpdatedAt && <p>供应商更新时间：{event.providerUpdatedAt} UTC</p>}
    </details>
    <MacroExplanation key={event.snapshotId} event={event} />
  </aside>;
}

export default function MacroCalendar({ initialTimezone = 'America/New_York', initialEvent = null, preset = null, onClearPreset }) {
  const [zone, setZone] = useState(initialTimezone);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [group, setGroup] = useState('ALL');
  const [status, setStatus] = useState('ALL');
  const [windowStart] = useState(Date.now);
  const sevenDayMode = preset === '7d';
  const [range, setRange] = useState(() => sevenDayMode ? {start:dayKey(windowStart,'America/New_York'),end:dayKey(windowStart+7*86400000,'America/New_York')} : {start:'',end:''});
  const [selected, setSelected] = useState(initialEvent);
  const detail = useRef(null);
  useEffect(() => {
    if (!initialEvent || window.innerWidth > 1200) return;
    const timer=setTimeout(()=>detail.current?.scrollIntoView({behavior:'auto',block:'start'}),100);
    return ()=>clearTimeout(timer);
  }, []);
  useEffect(() => {
    let disposed = false, ac;
    async function load() {
      ac?.abort(); ac = new AbortController(); const current = ac;
      setBusy(true);
      try {
        const params = new URLSearchParams(Object.entries(range).filter(([, v]) => v));
        const body = await fetch(`/api/macro/calendar?${params}`, { signal: ac.signal }).then(jsonResponse);
        if (!disposed && !current.signal.aborted) { setData(body); setError(''); }
      } catch (err) { if (!disposed && err.name !== 'AbortError') setError(err.message); }
      finally { if (!disposed && !current.signal.aborted) setBusy(false); }
    }
    load();
    const timer = setInterval(() => { if (document.visibilityState === 'visible') load(); }, 60000);
    return () => { disposed = true; ac?.abort(); clearInterval(timer); };
  }, [range.start, range.end, refresh]);
  const all = [...(data?.events || []), ...(data?.observations || [])];
  const scoped = sevenDayMode ? sevenDayEvents(data?.events || [], windowStart) : all;
  const filtered = scoped.filter(e => (group === 'ALL' || e.group === group) && (status === 'ALL' || e.status === status));
  const chosen = selected || filtered.find(e => e.status === 'upcoming') || filtered.at(-1);
  // Freeze the selected evidence while the user reads or asks questions.
  useEffect(() => { if (!selected && chosen) setSelected(chosen); }, [selected, chosen]);
  const newest = chosen && all.find(e => e.id === chosen.id);
  const pick = e => { setSelected(e); if (window.innerWidth <= 1200) setTimeout(() => detail.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }), 0); };
  return <div className="macro-workspace">
    <div className="macro-toolbar">
      <div className="macro-filters" role="group" aria-label="事件类型">{Object.entries(groups).map(([id, label]) => <button key={id} aria-pressed={group === id} className={group === id ? 'active' : ''} onClick={() => { setGroup(id); setSelected(null); }}>{label}</button>)}</div>
      <div className="macro-tools"><select aria-label="日历时区" value={zone} onChange={e => setZone(e.target.value)}>{Object.entries(zones).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
        <button className="button" disabled={busy} onClick={() => setRefresh(r => r + 1)}><RefreshCw size={14} className={busy ? 'macro-spin' : ''} />刷新</button></div>
    </div>
    <div className="macro-source-status"><span className="macro-live-dot" />官方数据 <span>·</span> {data?.consensusStatus === 'connected' ? '公开预期参考已连接' : data?.consensusStatus === 'stale' ? '公开预期参考保留上次数据' : data?.publicForecastStatus?.sources?.some(s => s.status === 'ok') ? '公开预测已接入 · 按事件覆盖' : '公开预测待更新'}
      <span className="macro-check-time">{data ? `最近检查 ${time(data.checkedAt, zone)}` : '正在连接发布机构…'}</span></div>
    {data?.publicForecastStatus && <details className="macro-coverage macro-forecast-status"><summary>公开预测每日更新 · 悉尼时间 08:00{data.publicForecastStatus.lastAttemptAt ? ` · 最近检查 ${time(data.publicForecastStatus.lastAttemptAt, zone)}` : ' · 首次更新中'}</summary>
      <p>汇集公开来源，服务恢复后补充检查遗漏更新。请以来源时间和原文为准。</p>
      {data.publicForecastStatus.sources.map(s => <p key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.label || (s.id === 'scotia' ? 'Scotiabank 公开周报（调查与机构）' : 'Cleveland Fed（模型）')}</a> · {s.status === 'ok' ? `已取得 ${s.count} 条公开记录` : customerMessage(s.error)}</p>)}
    </details>}
    {error && <div className="macro-warning" role="alert">{customerMessage(error)}{data && ' 当前列表来自上次成功加载，不代表已刷新。'}</div>}
    {data?.warnings.length > 0 && <details className="macro-coverage"><summary>数据覆盖提示 · {data.warnings.length} 项</summary>{data.warnings.map(w => <p key={w}>{w}</p>)}</details>}
    <div className="macro-layout">
      <section className="macro-list panel">
        <div className="macro-list-heading"><h2>{sevenDayMode ? "未来 7 天宏观排期" : "经济发布日历"}</h2><span>{sevenDayMode && `${new Set(filtered.map(e=>e.group+"|"+e.releaseAt)).size} 场发布 · `}{filtered.length} 项指标</span></div>
        <div className="macro-range"><label>从<input type="date" disabled={sevenDayMode} aria-label="起始日期" value={range.start || data?.from || ''} onChange={e => { setRange(r => ({ start: e.target.value, end: r.end || data?.to || '' })); setSelected(null); setData(null); }} /></label>
          <label>至<input type="date" disabled={sevenDayMode} aria-label="结束日期" value={range.end || data?.to || ''} onChange={e => { setRange(r => ({ start: r.start || data?.from || '', end: e.target.value })); setSelected(null); setData(null); }} /></label>
          <select aria-label="公布状态" value={status} onChange={e => { setStatus(e.target.value); setSelected(null); }}><option value="ALL">全部状态</option><option value="upcoming">待公布</option><option value="released">已取得数据</option><option value="pending">等待核验</option></select></div>
        <p className="macro-range-note">{sevenDayMode ? <>从 {time(new Date(windowStart).toISOString(), zone)} 起未来七天，仅列已核验排期；同类同时间合并计场次，各项指标仍可分别查看。日期已确认但时刻未知的事件按美东日历日期计入。 <button className="button" onClick={onClearPreset}>查看完整日历</button></> : "范围按美东发布日期筛选，最多跨 120 天。无核验日期的最新序列另列。"}</p>
        <div className="macro-table-scroll"><table className="macro-table"><thead><tr><th>事件 / 发布时间<Help field="release" label="事件 / 发布时间" /></th><th>前值<Help field="previous" label="前值" /></th><th>公开预期参考<Help field="forecast" label="公开预期参考" /></th><th>实际<Help field="actual" label="实际" /></th></tr></thead><tbody>
          {filtered.map(e => <tr key={e.id} className={chosen?.id === e.id ? 'selected' : ''}>
            <td><button className="macro-event-button" onClick={() => pick(e)} aria-pressed={chosen?.id === e.id}><span className="macro-row-kind">{e.group} <em>{states[e.status]}{e.stale ? ' · 上次数据' : ''}</em></span><strong>{e.title}</strong><small>{releaseTime(e, zone)}</small></button><div className="macro-row-period">所属期<Help field="period" label="统计所属期" /> · {e.reference || '未提供'}</div></td>
            <td data-label="前值">{value(e.previous, '—')}</td><td data-label="公开预期参考">{value(e.forecast, '—')}</td><td data-label="实际" className={e.actual ? 'macro-actual' : 'macro-muted'}>{value(e.actual, e.status === 'upcoming' ? '待公布' : '未取得')}</td>
          </tr>)}
        </tbody></table></div>
        {!filtered.length && <div className="macro-empty"><Clock3 size={26} /><h3>{busy ? '正在读取官方数据…' : '当前范围没有可用事件'}</h3><p>可以切换事件类型或日期范围；缺失数据不会用演示值补齐。</p></div>}
        <div className="macro-list-footer">— 表示来源未提供，不代表零。点选事件查看口径与 AI 解读。</div>
      </section>
      <div ref={detail}>{chosen ? <EventDetail event={chosen} zone={zone} updated={newest && newest.snapshotId !== chosen.snapshotId} onUpdate={() => setSelected(newest)} /> : <aside className="macro-detail panel"><h3>选择一个事件</h3><p>查看数据、来源和对不同资产的可能影响。</p></aside>}</div>
    </div>
    <p className="macro-footnote">{data?.notice || '读取官方数据，保留来源与获取时间。'} 点击生成 AI 解读，查看事件背景、影响路径与研究依据。</p>
  </div>;
}
