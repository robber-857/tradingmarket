import { useEffect, useState } from "react";
import { RefreshCw, ArrowUpRight, Download } from "lucide-react";
import "./market-research.css";

export function useMarket(report, enabled) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    setBusy(enabled);
    if (!enabled) return () => controller.abort();
    fetch(`/api/research/${report.symbol}/market?snapshot_id=${report.snapshotId}`, {signal: controller.signal})
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "行情服务暂不可用。");
        return body;
      })
      .then((body) => { if (!controller.signal.aborted) setData(body); })
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof SyntaxError ? "行情服务暂时无法连接，请稍后刷新。" : e.message); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [report.symbol, report.snapshotId, enabled, revision]);
  return {data, error, busy, refresh: () => setRevision((n) => n + 1)};
}

const stamp = (value) => value ? new Date(value).toLocaleString("zh-CN", {timeZone: "America/New_York", hour12: false}) + " ET" : "时间不可得";

function PriceHistory({history, symbol}) {
  const [range, setRange] = useState(126);
  const [active, setActive] = useState(null);
  const rows = history.slice(-range);
  const values = rows.map((p) => p.close);
  const low = Math.min(...values), high = Math.max(...values), spread = high - low || 1;
  const x = (i) => 12 + i / Math.max(1, rows.length - 1) * 696;
  const y = (v) => 165 - (v - low) / spread * 135;
  const path = rows.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(p.close).toFixed(2)}`).join(" ");
  const selected = rows[Math.min(active ?? rows.length - 1, rows.length - 1)];
  return <div className="market-history">
    <div className="market-chart-heading">
      <div><strong>历史价格</strong><span>{selected ? `${selected.date} · $${selected.close.toFixed(2)}` : "暂无可用日线"}</span></div>
      <div className="segment">{[[21,"1M"],[126,"6M"],[600,"2Y"]].map(([n,label]) => <button key={n} className={range === n ? "active" : ""} aria-pressed={range === n} onClick={() => {setRange(n);setActive(null);}}>{label}</button>)}</div>
    </div>
    {rows.length > 1 ? <>
      <svg viewBox="0 0 720 194" role="img" aria-label={`${symbol} 拆股复权历史日收盘价，${rows[0].date} 至 ${rows.at(-1).date}`} onMouseLeave={() => setActive(null)} onMouseMove={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        setActive(Math.max(0,Math.min(rows.length-1,Math.round(((e.clientX-box.left)/box.width*720-12)/696*(rows.length-1)))));
      }}>
        {[30,97,165].map((v) => <line key={v} x1="12" x2="708" y1={v} y2={v} stroke="currentColor" opacity=".09" />)}
        <path d={`${path} L708,165 L12,165 Z`} fill="currentColor" opacity=".06" />
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
        {active != null && selected && <circle cx={x(Math.min(active, rows.length-1))} cy={y(selected.close)} r="4" fill="currentColor" />}
        <text x="12" y="189">{rows[0].date}</text><text x="708" y="189" textAnchor="end">{rows.at(-1).date}</text>
      </svg>
      <input className="market-chart-scrubber" type="range" min="0" max={rows.length-1} value={active ?? rows.length-1} onChange={(e) => setActive(+e.target.value)} aria-label="查看历史价格日期" aria-valuetext={`${selected?.date} ${selected?.close.toFixed(2)} 美元`} />
    </> : <div className="market-chart-empty">历史日线返回后在这里显示价格曲线</div>}
    <small>拆股复权日收盘价 · 不含分红再投资 · 不使用当日未完成日线</small>
  </div>;
}

export default function MarketResearch({market, symbol, enabled, onAsk}) {
  const {data, error, busy, refresh} = market;
  const quote = data?.quote, beta = data?.beta;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));
    const a=document.createElement("a"); a.href=url; a.download=`${symbol}-market-${data.marketSnapshotId}.json`; a.click(); URL.revokeObjectURL(url);
  };
  return <section className="panel market-research" id="market-prices" aria-busy={busy}>
    <div className="market-heading"><div><span className="eyebrow">MARKET CONTEXT</span><h2>行情与市场敏感度</h2></div>
      <button className="button" onClick={refresh} disabled={busy || !enabled}><RefreshCw size={14} className={busy ? "market-spin" : ""}/>{busy ? "正在获取" : "刷新行情"}</button>
    </div>
    {!enabled ? <p className="r-alert">历史报告期保留独立估值。切回「最新可得」报告期，即可启用当前报价、自动倍数和 Beta，避免混淆历史与当前时点。</p> : <>
      {busy && <p role="status" className="market-loading">正在核对报价、股票与 SPY 日线。首次加载通常需要约半分钟，缓存命中后更快。</p>}
      {error && <p role="alert" className="r-alert">{error}</p>}
      <div className="market-body">
        <div>
          <div className="market-quote"><span>{symbol} / USD</span><strong>{quote ? `$${quote.price.toFixed(2)}` : "—"}</strong><em>{quote ? quote.stale ? "报价过期 · 未用于估值" : quote.marketOpen ? "交易时段报价" : "最近可得报价 · 休市" : "等待数据源"}</em></div>
          <p className="market-timestamp">报价时间 {stamp(quote?.asOf)}</p>
          <PriceHistory key={data?.marketSnapshotId || symbol} history={data?.history || []} symbol={symbol}/>
        </div>
        <aside className="market-beta">
          <span>相对 SPY 的历史 Beta</span><strong>{beta ? beta.beta.toFixed(3) : "—"}</strong>
          <p>β = Cov(股票日收益率, SPY 日收益率) / Var(SPY 日收益率)</p>
          <dl><div><dt>样本</dt><dd>{beta ? `${beta.observations} 组日收益率` : "等待配对日线"}</dd></div><div><dt>拟合 R²</dt><dd>{beta?.rSquared != null ? `${(beta.rSquared*100).toFixed(1)}%` : "—"}</dd></div><div><dt>区间</dt><dd>{beta ? `${beta.start} — ${beta.end}` : "最多两年"}</dd></div></dl>
          <button className="ask" disabled={!beta} onClick={() => onAsk("当前历史 Beta 和 R² 分别说明什么？结合样本口径，哪些风险不能用 Beta 解释？")}>解读市场敏感度 <ArrowUpRight size={12}/></button>
          <small>历史价格回归，不是未来风险预测。CAPM 试算会自动带入此 Beta。</small>
        </aside>
      </div>
      {!!data?.issues.length && <details className="market-issues"><summary>数据状态 · {data.issues.length} 项待核对</summary>{data.issues.map((s,i)=><p key={i}>{s}</p>)}</details>}
      <footer><span>来源 <a href="https://twelvedata.com" target="_blank" rel="noreferrer">Twelve Data</a> · 默认实时源覆盖部分交易场所</span>{data && <button onClick={download}><Download size={12}/>导出行情与计算依据</button>}</footer>
    </>}
  </section>;
}
