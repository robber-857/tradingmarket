import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Calculator,
  Check,
  ChevronDown,
  CircleHelp,
  Download,
  ExternalLink,
  FileCheck2,
  Info,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import "./research.css";
import AIResearch from "./AIResearch";
import StockSearch from "./StockSearch";
import MarketResearch, { useMarket } from "./MarketResearch";
import { BetaEstimator, RelativeValuation, MethodGuide } from "./ResearchTools";

const labels = {
  revenue: "营业收入",
  gross_profit: "毛利润",
  operating_income: "营业利润",
  net_income: "净利润",
  eps: "稀释 EPS",
  diluted_shares: "加权平均稀释股数",
  operating_cash_flow: "经营现金流",
  capex: "资本性现金支出",
  free_cash_flow: "现金流减资本支出",
  stock_compensation: "股权激励费用",
  interest: "利息费用",
  assets: "总资产",
  liabilities: "总负债",
  equity: "归属母公司权益",
  total_equity: "总权益（含少数股东）",
  cash: "现金与现金等价物",
  debt: "已映射账面有息债务",
  shares: "期末 / 申报前流通股数",
  current_assets: "流动资产",
  current_liabilities: "流动负债",
  gross_margin: "毛利率",
  operating_margin: "营业利润率",
  net_margin: "净利润率",
  revenue_yoy: "营收同比",
  revenue_qoq: "营收环比",
  gross_margin_yoy: "毛利率同比变动",
  profit_yoy: "净利润同比",
  profit_qoq: "净利润环比",
  capex_intensity: "资本开支 / 营收",
  cash_conversion: "经营现金流 / 净利润",
  liability_ratio: "总负债率",
  current_ratio: "流动比率",
  net_debt: "净债务（现金口径）",
  share_dilution_yoy: "稀释股数同比",
  interest_coverage: "利息覆盖倍数",
};
const kinds = {
  eps: "eps",
  diluted_shares: "shares",
  shares: "shares",
  gross_margin: "percent",
  operating_margin: "percent",
  net_margin: "percent",
  revenue_yoy: "percent",
  revenue_qoq: "percent",
  profit_yoy: "percent",
  profit_qoq: "percent",
  gross_margin_yoy: "pp",
  capex_intensity: "percent",
  cash_conversion: "multiple",
  liability_ratio: "percent",
  current_ratio: "multiple",
  share_dilution_yoy: "percent",
  interest_coverage: "multiple",
};
const sources = [
  [
    "SEC · 官方财报数据",
    "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
  ],
  [
    "CFA · FCFF 与 WACC",
    "https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation",
  ],
  [
    "Damodaran · 企业估值",
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html",
  ],
  [
    "Damodaran · 终值与再投资",
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm",
  ],
];
function fmt(value, kind = "money") {
  if (value == null || !Number.isFinite(value)) return "—";
  if (kind === "percent") return `${(value * 100).toFixed(1)}%`;
  if (kind === "pp")
    return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
  if (kind === "multiple") return `${value.toFixed(2)}×`;
  if (kind === "number") return value.toFixed(3);
  if (kind === "eps" || kind === "price") return `$${value.toFixed(2)}`;
  return `${kind === "shares" ? "" : "$"}${(value / 1e9).toFixed(2)}B`;
}
function errorText(data) {
  return typeof data.detail === "string"
    ? data.detail
    : Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg).join("；")
      : "计算服务暂不可用。";
}
async function getJSON(url, options = {}) {
  const r = await fetch(url, options);
  const text = await r.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("研究服务暂时无法连接，请稍后重试。");
  }
  if (!r.ok) throw new Error(errorText(data));
  return data;
}
function saveJSON(data, name) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
function Value({ data, metric, onInspect }) {
  return (
    <button
      className={`evidence-value ${data?.value == null ? "unavailable" : ""}`}
      onClick={() =>
        onInspect({
          title: labels[metric] || metric,
          data,
          kind: kinds[metric],
        })
      }
      title="查看公式、报告期与原始来源"
    >
      {fmt(data?.value, kinds[metric])}
      <ArrowUpRight size={11} />
    </button>
  );
}
function Inspector({ item, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const prior = document.activeElement;
    ref.current?.querySelector("button")?.focus();
    const listener = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const nodes = ref.current?.querySelectorAll("button,a[href]");
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", listener);
      document.body.style.overflow = old;
      prior?.focus();
    };
  }, [onClose]);
  const d = item.data;
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="modal evidence-modal"
        role="dialog"
        aria-modal="true"
        aria-label="指标计算与来源"
        ref={ref}
      >
        <button
          className="modal-close icon-button"
          aria-label="关闭指标详情"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <span className="badge green">计算与证据</span>
        <h2>{item.title}</h2>
        <div className="evidence-number">{fmt(d?.value, item.kind)}</div>
        <p>
          {d?.formula ||
            (d?.status === "disclosed"
              ? "官方财报披露值"
              : d?.reason || "当前无法计算")}
        </p>
        {d?.warning && <div className="r-alert">{d.warning}</div>}
        <h3>原始输入与出处</h3>
        {d?.sourceUrl && <p><a href={d.sourceUrl} target="_blank" rel="noreferrer">Twelve Data 数据来源与口径 <ExternalLink size={12}/></a>{d.retrievedAt && <small> · 采集于 {d.retrievedAt}</small>}</p>}
        {d?.evidence?.map((e, i) => (
          <article
            className="source-record"
            key={`${e.accession}-${e.tag}-${e.start}-${e.end}-${i}`}
          >
            <div>
              <b>
                {Number(e.value).toLocaleString("en-US", {
                  maximumFractionDigits: 4,
                })}
              </b>
              <span>{e.unit}</span>
            </div>
            <p>
              {e.start ? `${e.start} → ` : ""}
              {e.end} · {e.form} · {e.filed} 提交
            </p>
            <a href={e.url} target="_blank" rel="noreferrer">
              查看原始财报
              <ExternalLink size={12} />
            </a>
          </article>
        ))}
        {!d?.evidence?.length && !d?.sourceUrl && (
          <p>
            {d?.value == null
              ? "没有完整输入时不生成估计值。缺失不等于零。"
              : "此项根据你的假设与估值公式计算，详见估值参数与计算明细；不是官方预测。"}
          </p>
        )}
        <p className="fine-print">
          展示最新可得修订口径，可能来自后续申报。币种为 USD，B 代表十亿美元。
        </p>
      </section>
    </div>
  );
}
function Trend({ quarters, metric, onSelect }) {
  const values = quarters.map((q) => q.flow[metric]?.value);
  const max = Math.max(1, ...values.filter((v) => v != null));
  const min = Math.min(0, ...values.filter((v) => v != null));
  const y = (v) => 165 - ((v - min) / (max - min)) * 135;
  const zero = y(0);
  return (
    <div className="r-trend">
      <svg
        viewBox="0 0 760 210"
        role="img"
        aria-label={`${labels[metric]}历史季度趋势`}
      >
        <line x1="10" x2="750" y1={zero} y2={zero} stroke="var(--border)" />
        {quarters.map((q, i) => {
          const value = values[i];
          return (
            <g
              key={q.end}
              onClick={() => onSelect(q.end)}
              className="r-bar-group"
            >
              <title>
                {q.end}: {fmt(value)}
              </title>
              <rect
                x={22 + i * 92}
                y={value == null ? zero : Math.min(y(value), zero)}
                width="53"
                height={
                  value == null ? 1 : Math.max(1, Math.abs(y(value) - zero))
                }
                rx="3"
                fill={
                  value < 0
                    ? "var(--danger)"
                    : i === quarters.length - 1
                      ? "var(--text)"
                      : "var(--border-strong)"
                }
              />
              <text
                x={48 + i * 92}
                y={
                  value == null
                    ? zero - 10
                    : value >= 0
                      ? y(value) - 10
                      : y(value) + 15
                }
                textAnchor="middle"
                fontSize="10"
                fill="var(--muted)"
              >
                {value == null ? "—" : `${(value / 1e9).toFixed(1)}B`}
              </text>
              <text
                x={48 + i * 92}
                y="195"
                textAnchor="middle"
                fontSize="9"
                fill="var(--muted)"
              >
                {q.end.slice(2)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function ResearchWorkspace({
  mode,
  symbol = "INTC",
  onSymbolChange,
  isWatched,
  onToggleWatch,
}) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [end, setEnd] = useState("");
  const [tab, setTab] = useState("利润与增长");
  const [inspect, setInspect] = useState(null);
  const [trend, setTrend] = useState("revenue");
  const supported = !["BTC", "ETH", "USDT"].includes(symbol);
  useEffect(() => {
    if (!supported) {
      setReport(null);
      return;
    }
    const c = new AbortController();
    setLoading(true);
    setReport(null);
    setError("");
    getJSON(`/api/research/${encodeURIComponent(symbol)}${reload ? "?refresh=true" : ""}`, {
      signal: c.signal,
    })
      .then((data) => {
        if (c.signal.aborted) return;
        setReport(data);
        const remembered = sessionStorage.getItem(
          `meridian-report-period-${symbol}`,
        );
        setEnd(
          data.quarters.some((q) => q.end === remembered)
            ? remembered
            : data.latestReportEnd,
        );
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [symbol, reload, supported]);
  useEffect(() => {
    if (report?.symbol === symbol && report.quarters.some((q) => q.end === end))
      sessionStorage.setItem(`meridian-report-period-${symbol}`, end);
  }, [report, symbol, end]);
  const quarter = report?.symbol === symbol
    ? report.quarters.find((q) => q.end === end) || report.quarters[0]
    : null;
  return (
    <div className="real-research">
      <StockSearch symbol={symbol} onSelect={(next) => {setInspect(null); onSymbolChange(next);}} />
      {!supported ? (
        <section className="panel empty-state">
          <FileCheck2 size={38} />
          <h2>{symbol} 暂不适用这套公司财务模型</h2>
          <p>
            BTC、ETH
            不具备公司的三张财务报表。链上与代币估值应使用独立模型；此处不会套用股票
            DCF。
          </p>
          <button
            className="button primary"
            onClick={() => onSymbolChange("INTC")}
          >
            研究 Intel
            <ArrowRight size={15} />
          </button>
        </section>
      ) : loading ? (
        <section className="panel research-loading" role="status">
          <RefreshCw size={23} />
          <h3>正在核对 {symbol} 的正式申报</h3>
          <p>匹配报告期、还原季度现金流、计算 TTM 与来源证据。</p>
          <div className="skeleton-line" />
          <div className="skeleton-line short" />
        </section>
      ) : error ? (
        <section className="panel empty-state">
          <Info size={30} />
          <h2>暂时无法生成该证券的研究</h2>
          <p role="alert">{error}</p>
          <button
            className="button primary"
            onClick={() => setReload((v) => v + 1)}
          >
            <RefreshCw size={15} />
            重试
          </button>
          <p>不会使用演示数据或语言模型补齐缺失财报。</p>
        </section>
      ) : (
        quarter && (
          <>
            <section className="r-report-header">
              <div className="r-company-icon">
                {symbol === "INTC" ? "in" : symbol[0]}
              </div>
              <div className="r-company">
                <span className="eyebrow">
                  {mode === "financials"
                    ? "FINANCIAL INTELLIGENCE"
                    : "FUNDAMENTAL VALUATION"}
                </span>
                <h2>
                  {report.company.name}
                  <span>{symbol}</span>
                </h2>
                <p>{report.company.english} · USD · US GAAP</p>
              </div>
              <div className="r-report-actions">
                <button className="button" onClick={onToggleWatch}>
                  {isWatched ? <Check size={14} /> : <PlusIcon />}
                  {isWatched ? "已关注" : "关注公司"}
                </button>
                <button
                  className="icon-button"
                  aria-label="刷新官方财报"
                  onClick={() => setReload((v) => v + 1)}
                >
                  <RefreshCw size={16} />
                </button>
              </div>
            </section>
            <div className="r-period-row">
              <div>
                <span className="r-verified">
                  <FileCheck2 size={14} />
                  官方披露
                </span>
                <span className="r-period-note">
                  {quarter.filing.form} · {quarter.filing.filed} 提交
                </span>
                <a href={quarter.filing.url} target="_blank" rel="noreferrer">
                  原始报告
                  <ExternalLink size={12} />
                </a>
              </div>
              <label>
                报告期末
                <select
                  aria-label="选择财报报告期"
                  value={quarter.end}
                  onChange={(e) => setEnd(e.target.value)}
                >
                  {report.quarters.map((q) => (
                    <option key={q.end} value={q.end}>
                      {q.end}
                      {q.end === report.latestReportEnd ? " · 最新可得" : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {report.sources.some((s) => s.stale) && (
              <div className="r-alert" role="status">
                SEC
                更新失败，当前使用历史缓存。采集时间见下方来源记录，不代表最新申报。
              </div>
            )}
            {report.latestFiledReportEnd !== report.latestReportEnd && report.latestFiledReportEnd && <p className="r-alert">最新申报期 {report.latestFiledReportEnd} 尚无法完整映射，当前展示可解析的报告期；请核对最新原文。</p>}
            {report.company.industry && <p className="stock-coverage-note">{report.company.exchange} · {report.company.industry} · CIK {report.company.cik}</p>}
            {mode === "financials" ? (
              <>
                <section className="r-takeaways">
                  <div className="r-section-heading">
                    <span className="eyebrow">
                      THE THREE THINGS THAT MATTER
                    </span>
                    <span className="badge">按财报与公式计算</span>
                  </div>
                  <div className="r-insight-grid">
                    {quarter.insights.map((item, i) => (
                      <article key={item.title}>
                        <span className="r-step">0{i + 1}</span>
                        <h3>{item.title}</h3>
                        <p>{item.text}</p>
                        <small>{item.kind}</small>
                      </article>
                    ))}
                  </div>
                </section>
                <div className="r-kpis">
                  {[
                    "revenue",
                    "operating_margin",
                    "free_cash_flow",
                    "share_dilution_yoy",
                  ].map((key) => {
                    const d = quarter.flow[key] || quarter.metrics[key];
                    return (
                      <div key={key}>
                        <span>{labels[key]}</span>
                        <Value data={d} metric={key} onInspect={setInspect} />
                        <small>
                          {key === "revenue"
                            ? `同比 ${fmt(quarter.metrics.revenue_yoy.value, "percent")} · 环比 ${fmt(quarter.metrics.revenue_qoq.value, "percent")}`
                            : key === "free_cash_flow"
                              ? "经营现金流 − 资本支出（单季）"
                              : key === "share_dilution_yoy"
                                ? "非持股比例预测；拆股需复核"
                                : `报告期间 ${quarter.start} — ${quarter.end}`}
                        </small>
                      </div>
                    );
                  })}
                </div>
                <AIResearch
                  key={`${report.snapshotId}-${quarter.end}`}
                  report={report}
                  quarter={quarter}
                  mode="financials"
                  onInspect={setInspect}
                />
                <section className="panel r-financial-panel">
                  <div className="r-section-heading">
                    <h2>财务证据，一眼看清</h2>
                    <div className="segment">
                      <button
                        className={trend === "revenue" ? "active" : ""}
                        onClick={() => setTrend("revenue")}
                      >
                        营收趋势
                      </button>
                      <button
                        className={trend === "free_cash_flow" ? "active" : ""}
                        onClick={() => setTrend("free_cash_flow")}
                      >
                        现金流趋势
                      </button>
                    </div>
                  </div>
                  <Trend
                    quarters={[...report.quarters].reverse()}
                    metric={trend}
                    onSelect={setEnd}
                  />
                  <div className="tabs">
                    {["利润与增长", "现金流质量", "资产负债", "数据与方法"].map(
                      (t) => (
                        <button
                          key={t}
                          className={tab === t ? "active" : ""}
                          onClick={() => setTab(t)}
                        >
                          {t}
                        </button>
                      ),
                    )}
                  </div>
                  {tab === "数据与方法" ? (
                    <MethodPanel report={report} />
                  ) : (
                    <FinancialTable
                      tab={tab}
                      quarter={quarter}
                      report={report}
                      onInspect={setInspect}
                    />
                  )}
                </section>
                <div className="r-boundary">
                  <Info size={18} />
                  <div>
                    <strong>财报好，不等于股价一定涨。</strong>
                    <p>
                      当前没有接入一致预期、实时行情与指引全文，因此不推断“超预期”或财报后股价下跌的原因。先区分业绩事实、市场预期和估值假设。
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <ValuationPanel
                key={`${report.snapshotId}-${quarter.end}`}
                report={report}
                quarter={quarter}
                onInspect={setInspect}
              />
            )}
            <div className="r-source-footer">
              <span>
                <ShieldCheck size={13} />
                SEC 官方数据 · 最新可得修订口径
              </span>
              <span>
                采集于{" "}
                {new Date(report.sources[0]?.retrievedAt).toLocaleString(
                  "zh-CN",
                  { timeZone: "Australia/Sydney", hour12: false },
                )}
                （悉尼）
              </span>
              <button
                onClick={() =>
                  saveJSON(
                    report,
                    `${symbol}-${quarter.end}-financial-evidence.json`,
                  )
                }
              >
                <Download size={13} />
                导出研究数据
              </button>
            </div>
          </>
        )
      )}
      {inspect && <Inspector item={inspect} onClose={() => setInspect(null)} />}
    </div>
  );
}
function PlusIcon() {
  return <span aria-hidden="true">＋</span>;
}
function FinancialTable({ tab, quarter, report, onInspect }) {
  const index = report.quarters.findIndex((q) => q.end === quarter.end);
  const previous = report.quarters[index + 1];
  const yoy = report.quarters.find((q) => {
    const days = (new Date(quarter.end) - new Date(q.end)) / 86400000;
    return days >= 350 && days <= 380;
  });
  const cols = [quarter, previous, yoy];
  const metrics =
    tab === "利润与增长"
      ? [
          "revenue",
          "gross_profit",
          "gross_margin",
          "operating_income",
          "operating_margin",
          "net_income",
          "profit_yoy",
          "profit_qoq",
          "eps",
          "diluted_shares",
        ]
      : tab === "现金流质量"
        ? [
            "operating_cash_flow",
            "capex",
            "free_cash_flow",
            "cash_conversion",
            "stock_compensation",
            "capex_intensity",
          ]
        : [
            "assets",
            "liabilities",
            "equity",
            "cash",
            "debt",
            "net_debt",
            "liability_ratio",
            "current_ratio",
            "shares",
          ];
  return (
    <>
      <div className="table-wrap">
        <table className="r-financial-table">
          <thead>
            <tr>
              <th>
                指标 <span>点击数字查看出处</span>
              </th>
              {cols.map((q, i) => (
                <th key={i}>
                  {["本季 / 期末", "上季 / 期末", "上年同季 / 期末"][i]}
                  <small>{q?.end || "不可得"}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((key) => (
              <tr key={key}>
                <td>{labels[key]}</td>
                {cols.map((q, i) => (
                  <td key={i}>
                    <Value
                      metric={key}
                      data={q?.flow[key] || q?.metrics[key] || q?.stock[key]}
                      onInspect={onInspect}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {tab === "现金流质量" && (
        <div className="r-ttm-summary">
          <span>近四季 TTM</span>
          <div>
            <small>经营现金流</small>
            <Value
              metric="operating_cash_flow"
              data={quarter.ttm.operating_cash_flow}
              onInspect={onInspect}
            />
          </div>
          <div>
            <small>现金流减资本支出</small>
            <Value
              metric="free_cash_flow"
              data={quarter.ttm.free_cash_flow}
              onInspect={onInspect}
            />
          </div>
          <div>
            <small>现金利润比</small>
            <Value
              metric="cash_conversion"
              data={quarter.ttm.cash_conversion}
              onInspect={onInspect}
            />
          </div>
        </div>
      )}
      <p className="r-table-note">
        B = 十亿美元；股数 B = 十亿股；pp =
        百分点。单季现金流由同财年累计值差分，缺失显示「—」。EPS
        与加权平均股数不做累计差分。
      </p>
    </>
  );
}
function MethodPanel({ report }) {
  return (
    <div className="r-method">
      <div>
        <h3>事实、解读与假设分开</h3>
        <p>
          财务数字取自正式 10-Q /
          10-K；增长率和比率按下列公式计算。摘要提炼关键财务变化，AI 解读区进一步解释数据，
          并区分事实、推论和条件假设。均不代表买卖评级。
        </p>
        <h3>使用什么公式？</h3>
        <code>营收同比 = 本季营收 / 上年同季营收 − 1</code>
        <code>现金利润比 = 经营现金流 / 正值净利润</code>
        <code>FCF 展示口径 = 经营现金流 − 资本性现金支出</code>
        <p>
          展示 FCF 不直接送入 FCFF
          估值。亏损基期不计算常规增长率；四个季度不连续时不生成 TTM。
        </p>
      </div>
      <div>
        <h3>来源与模型边界</h3>
        {report.limitations.map((t) => (
          <p key={t}>{t}</p>
        ))}
        {sources.map(([t, u]) => (
          <a href={u} key={u} target="_blank" rel="noreferrer">
            {t}
            <ExternalLink size={12} />
          </a>
        ))}
      </div>
    </div>
  );
}

function ValuationPanel({ report, quarter, onInspect }) {
  const dcfAllowed = report.capabilities?.dcf !== false;
  const marketEnabled = quarter.end === report.latestReportEnd;
  const market = useMarket(report, marketEnabled);
  const [params, setParams] = useState(() => ({
    growth: 8,
    target_margin: Math.min(
      65,
      Math.max(5, (quarter.ttm.operating_margin.value ?? 0.15) * 100),
    ),
    tax_rate: 25,
    wacc: 10,
    terminal_growth: 2.5,
    sales_to_capital: 2,
    terminal_roic: 12,
    excess_cash: 0,
    nonoperating_assets: 0,
    debt:
      quarter.stock.debt.value == null ? "" : quarter.stock.debt.value / 1e9,
    other_claims:
      quarter.stock.total_equity.value == null ||
      quarter.stock.equity.value == null
        ? ""
        : Math.max(
            0,
            quarter.stock.total_equity.value - quarter.stock.equity.value,
          ) / 1e9,
    shares:
      quarter.stock.shares.value == null
        ? ""
        : quarter.stock.shares.value / 1e9,
    comparison_price: "",
  }));
  const sharesEdited = useRef(false);
  useEffect(() => {
    if (!sharesEdited.current && market.data?.multiples.shares)
      setParams((p) => ({...p, shares: market.data.multiples.shares / 1e9}));
  }, [market.data?.marketSnapshotId]);
  const [result, setResult] = useState(null);
  const [calcError, setCalcError] = useState("");
  const [busy, setBusy] = useState(false);
  const [waccOpen, setWaccOpen] = useState(false);
  const [capitalEvidence, setCapitalEvidence] = useState(null);
  const [aiPrompt, setAiPrompt] = useState(null);
  const jump = (id) => {
    const node = document.getElementById(id);
    if (node?.tagName === "DETAILS") node.open = true;
    node?.scrollIntoView({
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
  };
  const askMetric = (text) => {
    setAiPrompt({ text, id: Date.now() });
    jump("research-ai");
  };
  const percentFields = [
    "growth",
    "target_margin",
    "tax_rate",
    "wacc",
    "terminal_growth",
    "terminal_roic",
  ];
  const billionFields = [
    "excess_cash",
    "nonoperating_assets",
    "debt",
    "other_claims",
    "shares",
  ];
  useEffect(() => {
    const c = new AbortController();
    if (!dcfAllowed) {setResult(null);setBusy(false);setCalcError(report.capabilities.dcfReason);return () => c.abort();}
    setBusy(true);
    setResult(null);
    setCalcError("");
    const timeout = setTimeout(() => {
      const assumptions = {};
      for (const [k, v] of Object.entries(params)) {
        if (k === "comparison_price") {
          assumptions[k] = v === "" ? null : Number(v);
          continue;
        }
        if (v === "" || !Number.isFinite(Number(v))) {
          setCalcError("请完整填写计算参数；缺失输入不会自动补零。");
          setBusy(false);
          return;
        }
        assumptions[k] =
          Number(v) *
          (percentFields.includes(k)
            ? 0.01
            : billionFields.includes(k)
              ? 1e9
              : 1);
      }
      getJSON(`/api/research/${report.symbol}/valuation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: c.signal,
        body: JSON.stringify({
          snapshot_id: report.snapshotId,
          report_end: quarter.end,
          assumptions,
          market_snapshot_id: market.data?.marketSnapshotId || null,
        }),
      })
        .then((data) => {if (!c.signal.aborted) setResult(data);})
        .catch((e) => {
          if (e.name !== "AbortError") setCalcError(e.message);
        })
        .finally(() => {
          if (!c.signal.aborted) setBusy(false);
        });
    }, 280);
    return () => {
      clearTimeout(timeout);
      c.abort();
    };
  }, [params, report.snapshotId, report.symbol, quarter.end, market.data?.marketSnapshotId]);
  const update = (key, v) => {
    if (key === "shares") sharesEdited.current = true;
    if (key === "wacc" || key === "tax_rate") setCapitalEvidence(null);
    setParams((p) => ({ ...p, [key]: v }));
  };
  return (
    <>
      <nav className="research-subnav" aria-label="基本面研究章节">
        {[
          ["fundamental-quality", "经营质量"],
          ["market-prices", "行情与 Beta"],
          ["relative-value", "相对估值"],
          ["dcf-workbench", "DCF 情景"],
          ["research-ai", "AI 解读"],
          ["research-methods", "指标解释"],
        ].map(([id, label]) => (
          <button key={id} onClick={() => jump(id)}>
            {label}
          </button>
        ))}
      </nav>
      <div className="r-valuation-intro">
        <div>
          <span className="eyebrow">VALUE IS A SET OF ASSUMPTIONS</span>
          <h2>这家公司，要怎样增长才支撑估值？</h2>
          <p>基于已披露经营数据，调整假设，查看价值如何变化。</p>
        </div>
        <span className="badge assumption">情景模型 · 非目标价</span>
      </div>
      <div className="r-kpis valuation-kpis" id="fundamental-quality">
        <div>
          <span>TTM 营收</span>
          <Value
            metric="revenue"
            data={quarter.ttm.revenue}
            onInspect={onInspect}
          />
          <small>连续四个独立季度</small>
        </div>
        <div>
          <span>TTM 营业利润率</span>
          <Value
            metric="operating_margin"
            data={quarter.ttm.operating_margin}
            onInspect={onInspect}
          />
          <small>营业利润 / 收入</small>
        </div>
        <div>
          <span>简化 ROIC</span>
          <strong>{busy ? "计算中" : fmt(result?.roic, "percent")}</strong>
          <small>
            {result && result.roic == null
              ? "投入资本缺失或非正，或营业利润为负，暂不计算"
              : "基于所选税率与平均投入资本"}
          </small>
        </div>
        <div>
          <span>ROIC − WACC</span>
          <strong>{busy ? "计算中" : fmt(result?.roicSpread, "pp")}</strong>
          <small>非风险评级；负值表示模型资本回报承压</small>
        </div>
      </div>
      <MarketResearch market={market} symbol={report.symbol} enabled={marketEnabled} onAsk={askMetric}/>
      <RelativeValuation
        result={result}
        busy={market.busy}
        market={market.data}
        marketEnabled={marketEnabled}
        onAsk={askMetric}
      />
      {!dcfAllowed ? <section className="panel r-method" id="dcf-workbench"><h2>当前估值模型不适用</h2><p>{report.capabilities.dcfReason}</p><p>仍可查看已披露财报、行情与历史 Beta，并向 AI 追问这些数据。</p></section> : <div className="valuation-workbench" id="dcf-workbench">
        <section className="panel assumption-panel">
          <div className="r-section-heading">
            <h2>
              <SlidersHorizontal size={17} />
              调整关键假设
            </h2>
            <CircleHelp size={15} />
          </div>
          <p className="r-assumption-note">
            初始值用于试算，不是经济学家推荐值、公司指引或市场一致预期。
          </p>
          {[
            ["growth", "未来五年营收增速", -30, 60, 0.5, "%"],
            ["target_margin", "第五年营业利润率", 0.5, 80, 0.5, "%"],
            ["wacc", "WACC 折现率", 2, 40, 0.25, "%"],
            ["terminal_growth", "永续增长率 g", 0, 5, 0.25, "%"],
          ].map(([k, t, min, max, step, unit]) => (
            <label className="r-slider" key={k}>
              <span>
                {t}
                <span>
                  <input
                    aria-label={t}
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={params[k]}
                    onChange={(e) => update(k, e.target.value)}
                  />
                  {unit}
                </span>
              </span>
              <input
                aria-label={`${t}滑块`}
                type="range"
                min={min}
                max={max}
                step={step}
                value={params[k] || min}
                onChange={(e) => update(k, e.target.value)}
              />
            </label>
          ))}
          <button
            className="r-wacc-link"
            onClick={() => setWaccOpen((v) => !v)}
          >
            <Calculator size={14} />
            WACC 怎么算？打开 CAPM 试算
            <ChevronDown size={13} />
          </button>
          {waccOpen && (
            <WaccBuilder
              key={market.data?.marketSnapshotId || "manual"}
              market={market.data}
              taxRate={params.tax_rate}
              onApply={(v, inputs, betaSample) => {
                update("wacc", +(v * 100).toFixed(3));
                setCapitalEvidence({ inputs, betaSample });
              }}
            />
          )}
          <div className="r-price-compare">
            <button onClick={() => jump("relative-value")}>
              查看报价与口径 <ArrowUpRight size={12} />
            </button>
            <div>
              <span>条件安全边际</span>
              <strong>
                {fmt(busy ? null : result?.base.marginOfSafety, "percent")}
              </strong>
              <small>1 − 行情快照价格 / 模型每股价值</small>
            </div>
          </div>
          <details className="r-advanced">
            <summary>
              再投资与税率假设
              <ChevronDown size={14} />
            </summary>
            <NumberField
              label="常态税率 (%)"
              name="tax_rate"
              params={params}
              onChange={update}
            />
            <NumberField
              label="销售 / 新增投入资本 (倍)"
              name="sales_to_capital"
              params={params}
              onChange={update}
            />
            <NumberField
              label="稳定期 ROIC (%)"
              name="terminal_roic"
              params={params}
              onChange={update}
            />
            <p>
              净再投资 = 正的营收增量 / 销售资本比。终值再投资率 = g / 稳定期
              ROIC。
            </p>
          </details>
          <details className="r-advanced">
            <summary>
              企业价值 → 每股价值
              <ChevronDown size={14} />
            </summary>
            <NumberField
              label="非经营现金 (十亿美元)"
              name="excess_cash"
              params={params}
              onChange={update}
            />
            <small>
              默认 0，不假设全部现金均可分配。披露现金：
              {fmt(quarter.stock.cash.value)}
            </small>
            <NumberField
              label="其他非经营资产 (十亿美元)"
              name="nonoperating_assets"
              params={params}
              onChange={update}
            />
            <NumberField
              label="有息债务 (十亿美元)"
              name="debt"
              params={params}
              onChange={update}
            />
            <small>初值采用已映射账面债务，尚未作债务市值与租赁调整。</small>
            <NumberField
              label="少数股东与其他索偿 (十亿美元)"
              name="other_claims"
              params={params}
              onChange={update}
            />
            <NumberField
              label="估值股数 (十亿股)"
              name="shares"
              params={params}
              onChange={update}
            />
            <small>
              初值来自披露流通股数，不含未来融资或回购预测。调整后属于用户假设。
            </small>
          </details>
        </section>
        <div className="valuation-output" aria-live="polite">
          {busy ? (
            <section className="panel r-calculating">
              <RefreshCw size={22} />
              <p>重新计算五年现金流与敏感性…</p>
            </section>
          ) : calcError ? (
            <section className="panel r-calculation-error" role="alert">
              <Info size={24} />
              <h3>这些参数暂时不能生成估值</h3>
              <p>{calcError}</p>
            </section>
          ) : (
            result && (
              <>
                <section className="panel scenario-results">
                  <div className="r-section-heading">
                    <h2>三种情景，三组假设</h2>
                    <span className="badge">无概率权重</span>
                  </div>
                  <div className="r-scenarios">
                    {result.scenarios.map((s) => (
                      <article
                        key={s.name}
                        className={s.name === "基准" ? "base" : ""}
                      >
                        <span>{s.name}</span>
                        <strong>{fmt(s.valuePerShare, "price")}</strong>
                        <small>每股条件估值</small>
                        <p>
                          营收增速 {fmt(s.assumptions?.growth, "percent")}
                          <br />
                          目标利润率{" "}
                          {fmt(s.assumptions?.target_margin, "percent")}
                          <br />
                          WACC {fmt(s.assumptions?.wacc, "percent")}
                        </p>
                      </article>
                    ))}
                  </div>
                  <p className="r-table-note">
                    悲观 / 乐观是在基准上调整增速 ±5pp、利润率 ±3pp、WACC ∓1pp
                    的压力测试。并非概率区间；高增长需要再投资，价值不保证按名称排序。
                  </p>
                  <div className="r-value-bridge">
                    <span>
                      经营资产价值
                      <strong>{fmt(result.base.enterpriseValue)}</strong>
                    </span>
                    <ArrowRight size={14} />
                    <span>
                      剩余股权价值
                      <strong>{fmt(result.base.equityResidual)}</strong>
                    </span>
                    <ArrowRight size={14} />
                    <span>
                      每股价值
                      <strong>{fmt(result.base.valuePerShare, "price")}</strong>
                    </span>
                  </div>
                  <div className="terminal-share">
                    <span>终值现值占企业价值</span>
                    <b>{fmt(result.base.terminal.weight, "percent")}</b>
                    <div>
                      <i
                        style={{
                          width: `${Math.min(100, Math.max(0, (result.base.terminal.weight || 0) * 100))}%`,
                        }}
                      />
                    </div>
                  </div>
                  {result.base.warnings.map((w) => (
                    <div className="r-alert" key={w}>
                      <Info size={14} />
                      {w}
                    </div>
                  ))}
                </section>
                <section className="panel sensitivity-panel">
                  <div className="r-section-heading">
                    <h2>最敏感的，往往是假设</h2>
                    <span className="badge">每股价值 / USD</span>
                  </div>
                  <p>行：WACC　列：永续增长率。无效组合留空。</p>
                  <div className="table-wrap">
                    <table className="sensitivity-table">
                      <thead>
                        <tr>
                          <th>WACC / g</th>
                          {result.sensitivity.growth.map((g, i) => (
                            <th key={i}>{fmt(g, "percent")}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.sensitivity.values.map((row, i) => (
                          <tr key={i}>
                            <th>
                              {fmt(result.sensitivity.wacc[i], "percent")}
                            </th>
                            {row.map((v, j) => (
                              <td
                                key={j}
                                className={i === 2 && j === 2 ? "center" : ""}
                                style={{
                                  background:
                                    i === 2 && j === 2
                                      ? undefined
                                      : `color-mix(in srgb, var(--text) ${(0.04 + (4 - i + j) * 0.025) * 100}%, transparent)`,
                                }}
                              >
                                {v == null ? "—" : v.toFixed(2)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )
          )}
        </div>
      </div>
      }
      {result && !busy && (
        <section className="panel valuation-audit">
          <div className="r-section-heading">
            <h2>从营收到估值，每一步都有账可查</h2>
            <button
              className="button"
              onClick={() =>
                saveJSON(
                  {
                    ...result,
                    evidence: report,
                    capitalInputs: capitalEvidence?.inputs || null,
                    betaSample: capitalEvidence?.betaSample || null,
                    market: market.data,
                    interpretation: "用户情景假设，非市场预测",
                  },
                  `${report.symbol}-${quarter.end}-valuation-audit.json`,
                )
              }
            >
              <Download size={14} />
              导出计算过程
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>预测年</th>
                  <th>营收</th>
                  <th>营业利润率</th>
                  <th>NOPAT</th>
                  <th>净再投资</th>
                  <th>FCFF</th>
                  <th>FCFF 现值</th>
                </tr>
              </thead>
              <tbody>
                {result.base.rows.map((r) => (
                  <tr key={r.year}>
                    <td>第 {r.year} 年</td>
                    <td>{fmt(r.revenue)}</td>
                    <td>{fmt(r.margin, "percent")}</td>
                    <td>{fmt(r.nopat)}</td>
                    <td>{fmt(r.reinvestment)}</td>
                    <td>{fmt(r.fcff)}</td>
                    <td>{fmt(r.presentValue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="r-formulas">
            <code>FCFF = EBIT − 经营税款 − 净再投资</code>
            <code>净再投资 ≈ max(Δ营收, 0) / 销售资本比</code>
            <code>终值 FCFF = 第6年 NOPAT × (1 − g / 稳定期 ROIC)</code>
            <code>EV = Σ FCFFₜ / (1 + WACC)ᵗ + 终值 / (1 + WACC)⁵</code>
            <code>股权价值 = EV + 非经营现金与资产 − 债务 − 其他索偿</code>
          </div>
          <p className="r-table-note">
            本模型对营业利润率作五年线性过渡；亏损年份不计税收返还或递延税盾。净再投资近似替代
            CapEx − D&A +
            Δ营运资本，未计并购、未来稀释、研发资本化及复杂租赁调整。固定
            WACC、年末折现。
          </p>
          <p className="r-table-note">
            {result.roicBasis}
          </p>
        </section>
      )}
      <AIResearch
        report={report}
        quarter={quarter}
        mode="fundamentals"
        assumptions={result?.base.assumptions || null}
        capitalEvidence={result ? capitalEvidence : null}
        marketSnapshotId={market.data?.marketSnapshotId || null}
        prompt={aiPrompt}
        available={!busy && !market.busy && (!result || (result.marketSnapshotId || null) === (market.data?.marketSnapshotId || null))}
        onInspect={onInspect}
      />
      <details className="panel r-method-collapse" id="research-methods">
        <summary>
          <BookOpen size={17} />
          公式依据、数据来源与模型适用范围
          <ChevronDown size={15} />
        </summary>
        <MethodGuide onAsk={askMetric} />
        <MethodPanel report={report} />
        <p>
          这些公式是成熟的估值工具，不是对某家公司价值的权威认证。本版仅为已映射非金融企业提供简化
          FCFF 研究；银行、保险、早期亏损企业和加密代币需另建模型。
        </p>
      </details>
    </>
  );
}
function NumberField({ label, name, params, onChange }) {
  return (
    <label className="r-number-field">
      <span>{label}</span>
      <input
        aria-label={label}
        type="number"
        step="any"
        value={params[name]}
        onChange={(e) => onChange(name, e.target.value)}
      />
    </label>
  );
}
function WaccBuilder({ taxRate, onApply, market }) {
  const [betaSample, setBetaSample] = useState(null);
  const [inputs, setInputs] = useState({
    risk_free: 4,
    beta: market?.beta && market.beta.beta >= 0 && market.beta.beta <= 5 ? +market.beta.beta.toFixed(3) : "",
    equity_risk_premium: 5,
    cost_of_debt: 5,
    equity_market_value: market?.multiples?.marketCap ? market.multiples.marketCap / 1e9 : "",
    debt_market_value: "",
  });
  const [output, setOutput] = useState(null);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);
  useEffect(() => {
    requestVersion.current++;
    setOutput(null);
  }, [taxRate]);
  return (
    <form
      className="wacc-builder"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        const version = ++requestVersion.current;
        try {
          const body = { tax_rate: Number(taxRate) / 100 };
          for (const [k, v] of Object.entries(inputs)) {
            if (v === "") throw new Error("请填写股权和债务的市场价值。");
            body[k] =
              Number(v) *
              (k.includes("market_value") ? 1e9 : k === "beta" ? 1 : 0.01);
          }
          const computed = await getJSON("/api/research-tools/wacc", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (version === requestVersion.current)
            setOutput({ ...computed, inputs: body });
        } catch (e) {
          if (version === requestVersion.current) {
            setOutput(null);
            setError(e.message);
          }
        }
      }}
    >
      <p>
        Beta 和股权市值在数据可用时自动带入。无风险利率、ERP、债务成本及债务市值仍需核实；市值估算未包含披露后的回购、增发。
      </p>
      {[
        ["risk_free", "无风险利率 (%)"],
        ["beta", "杠杆 Beta"],
        ["equity_risk_premium", "股权风险溢价 (%)"],
        ["cost_of_debt", "税前债务成本 (%)"],
        ["equity_market_value", "股权市值 (十亿美元)"],
        ["debt_market_value", "债务市值 (十亿美元)"],
      ].map(([k, t]) => (
        <NumberField
          key={k}
          label={t}
          name={k}
          params={inputs}
          onChange={(key, v) => {
            if (key === "beta") setBetaSample(null);
            requestVersion.current++;
            setInputs((p) => ({ ...p, [key]: v }));
            setOutput(null);
          }}
        />
      ))}
      <BetaEstimator
        onApply={(beta, sample) => {
          requestVersion.current++;
          setInputs((p) => ({ ...p, beta: +beta.toFixed(3) }));
          setBetaSample(sample);
          setOutput(null);
        }}
      />
      <button className="button" type="submit">
        计算 WACC
      </button>
      {error && <p role="alert">{error}</p>}
      {output && (
        <div className="wacc-result">
          <span>
            Ke {fmt(output.costOfEquity, "percent")} · WACC{" "}
            {fmt(output.wacc, "percent")}
          </span>
          <button
            className="button primary"
            type="button"
            onClick={() => onApply(output.wacc, output.inputs, betaSample)}
          >
            应用到估值
          </button>
        </div>
      )}
    </form>
  );
}
