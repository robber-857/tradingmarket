import { useRef, useState } from "react";
import { ArrowUpRight } from "lucide-react";

export const METHODS = [
  [
    "DCF",
    "现金流折现",
    "企业价值 = 未来 FCFF 的折现现值 + 终值现值",
    "用未来可分配现金估计经营资产价值，再扣债务等索偿得到股权价值。",
    "依赖增长、利润率、再投资和折现率；不是确定目标价。",
  ],
  [
    "FCFF",
    "企业自由现金流",
    "FCFF = EBIT × (1−T) + D&A − CapEx − Δ非现金营运资本",
    "本模型用 NOPAT − 净再投资计算；净再投资以收入增量/销售资本比近似。",
    "财报页的 CFO−CapEx 不直接等于 FCFF；亏损年份不计税收返还。",
  ],
  [
    "WACC",
    "加权平均资本成本",
    "WACC = E/(E+D) × Ke + D/(E+D) × Kd × (1−T)",
    "按股权与债务的市场价值加权，用于折现 FCFF。",
    "市值权重、税率和资本结构需要核实，不能用账面负债率替代。",
  ],
  [
    "CAPM",
    "资本资产定价模型",
    "Ke = Rf + β × ERP",
    "用无风险利率、股票相对市场的风险和风险溢价估计股权成本。",
    "这里的 Ke 是模型要求回报，不是承诺收益。",
  ],
  [
    "Beta",
    "市场敏感度",
    "β = Cov(资产收益率, 市场收益率) / Var(市场收益率)",
    "自动以股票和 SPY 的拆股复权日价格收益率估计 OLS Beta，也可导入独立样本。",
    "依赖基准、样本窗口与频率；不涵盖所有风险，也不保证未来稳定。",
  ],
  [
    "永续增长率",
    "稳定期增长 g",
    "稳定期再投资率 = g / ROIC",
    "预测期后持续增长仍需要资本投入。本模型将增长和稳定期资本回报联动。",
    "要求 g < WACC 且 g < 稳定期 ROIC；不宜无限外推高速增长。",
  ],
  [
    "终值",
    "预测期之后的价值",
    "TV = 第六年 FCFF / (WACC − g)",
    "表示预测期结束时后续现金流的价值，再折现回估值起点。",
    "终值占比越高，估值对远期假设通常越敏感。",
  ],
  [
    "P/E",
    "市盈率",
    "P/E = 行情价格 × 拆股修正已披露股数 / TTM 净利润",
    "看市场或情景价格对应多少倍过去的利润。",
    "亏损时不适用；一次性利润和周期高点会扭曲倍数。",
  ],
  [
    "P/B",
    "市净率",
    "P/B = 行情价格 × 拆股修正已披露股数 / 母公司账面权益",
    "比较股权价值与账面净资产。",
    "负权益时不适用；回购、研发费用化与无形资产影响可比性。",
  ],
  [
    "P/S",
    "市销率",
    "P/S = 行情价格 × 拆股修正已披露股数 / TTM 营收",
    "比较股权价值与收入规模。",
    "忽略利润率、现金消耗与负债；不能脱离盈利结构判断贵便宜。",
  ],
  [
    "ROIC",
    "投入资本回报",
    "ROIC ≈ TTM EBIT × (1−T) / 平均账面投入资本",
    "本模型投入资本为映射债务+总权益−现金，以本期和上年同期取平均。",
    "简化口径未调整研发、租赁或商誉；税率是假设，与 WACC 的比较是研究线索。",
  ],
];

export function MethodGuide({ onAsk }) {
  const [selected, setSelected] = useState("DCF");
  const method = METHODS.find((m) => m[0] === selected);
  return (
    <div className="method-guide">
      <h3>指标地图 · 从公式到理解</h3>
      <div className="method-chips">
        {METHODS.map((m) => (
          <button
            key={m[0]}
            onClick={() => setSelected(m[0])}
            aria-pressed={selected === m[0]}
          >
            {m[0]}
          </button>
        ))}
      </div>
      <div className="method-definition">
        <strong>
          {method[0]} · {method[1]}
        </strong>
        <code>{method[2]}</code>
        <p>{method[3]}</p>
        <small>{method[4]}</small>
        <button
          className="ask"
          onClick={() =>
            onAsk(
              `结合当前公司的数据和假设，解释 ${method[0]} 的含义、最重要的限制和需要验证的依据。`,
            )
          }
        >
          用当前公司追问 AI <ArrowUpRight size={12} />
        </button>
      </div>
    </div>
  );
}

export function RelativeValuation({
  result,
  busy,
  market,
  marketEnabled,
  onAsk,
}) {
  return (
    <section className="panel relative-panel" id="relative-value">
      <div className="relative-heading">
        <div>
          <span className="eyebrow">RELATIVE VALUATION</span>
          <h2>相对估值 · 三种观察角度</h2>
          <p>报价与最新正式财报自动计算。股数采用披露值并修正拆股，不含披露后回购、增发。</p>
        </div>
        <div className="market-price-auto">{marketEnabled ? "自动对比价格 · USD" : "历史报告期 · 行情联动暂停"}<strong>{market?.quote?.usable ? `$${market.quote.price.toFixed(2)}` : "—"}</strong><small>{market?.multiples.sharesAsOf ? `股数披露日 ${market.multiples.sharesAsOf}` : "等待已核验的行情数据"}</small></div>
      </div>
      <div className="relative-metrics">
        {[
          ["pe", "P/E", "市盈率"],
          ["pb", "P/B", "市净率"],
          ["ps", "P/S", "市销率"],
        ].map(([key, name, label]) => {
          const m = market?.multiples.metrics[key];
          return (
            <div key={key}>
              <h3>
                {name} <span>{label}</span>
              </h3>
              <strong>
                {busy
                  ? "计算中"
                  : m?.value == null
                    ? "—"
                    : `${m.value.toFixed(2)}×`}
              </strong>
              <p>
                {m?.reason ||
                  {
                    pe: "市值 / TTM 净利润",
                    pb: "市值 / 期末母公司权益",
                    ps: "市值 / TTM 营收",
                  }[key]}
              </p>
              <button
                onClick={() =>
                  onAsk(`结合当前数据，${name} 说明了什么，又容易忽略什么？`)
                }
              >
                解读此指标 <ArrowUpRight size={12} />
              </button>
            </div>
          );
        })}
      </div>
      <p className="r-table-note">
        低倍数不自动等于低估。应结合盈利持续性、资本结构和行业可比公司；当前不生成同业排名。
      </p>
    </section>
  );
}

export function BetaEstimator({ onApply }) {
  const [text, setText] = useState("");
  const [benchmark, setBenchmark] = useState("SPY");
  const [frequency, setFrequency] = useState("weekly");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  const invalidate = () => {
    version.current++;
    setResult(null);
    setError("");
    setBusy(false);
  };
  const calculate = async () => {
    const requestVersion = ++version.current;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const lines = text.trim().split(/\r?\n/).filter(Boolean);
      const rows = lines[0]?.toLowerCase().startsWith("date,")
        ? lines.slice(1)
        : lines;
      const prices = rows.map((line) => {
        const cols = line.split(",").map((x) => x.trim());
        if (cols.length !== 3 || cols.some((x) => !x))
          throw new Error(
            "每行需要日期、资产复权价格、基准复权价格，使用英文逗号分隔。",
          );
        return {
          date: cols[0],
          asset: Number(cols[1]),
          benchmark: Number(cols[2]),
        };
      });
      if (prices.length < 21 || prices.length > 1500)
        throw new Error(
          "请提供 21–1500 行按日期配对的价格，至少形成 20 个收益率观察值。",
        );
      const sample = { benchmark, frequency, prices };
      const response = await fetch("/api/research-tools/beta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sample),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "样本格式无效，请检查日期、正值价格与排列顺序。",
        );
      if (version.current === requestVersion) setResult({ data, sample });
    } catch (e) {
      if (version.current === requestVersion) setError(e.message);
    } finally {
      if (version.current === requestVersion) setBusy(false);
    }
  };
  return (
    <details className="beta-estimator">
      <summary>用历史价格估计 Beta</summary>
      <p>
        导入当前资产与基准的同频、同日复权价格。来源由你提供，模型不会自动核验行情。
      </p>
      <label>
        基准名称
        <input
          aria-label="Beta 基准名称"
          maxLength={30}
          value={benchmark}
          onChange={(e) => {
            invalidate();
            setBenchmark(e.target.value);
          }}
        />
      </label>
      <label>
        样本频率
        <select
          aria-label="Beta 样本频率"
          value={frequency}
          onChange={(e) => {
            invalidate();
            setFrequency(e.target.value);
          }}
        >
          <option value="daily">日频</option>
          <option value="weekly">周频</option>
          <option value="monthly">月频</option>
        </select>
      </label>
      <label>
        CSV：date,asset,benchmark
        <textarea
          aria-label="Beta 配对价格 CSV"
          maxLength={120000}
          value={text}
          onChange={(e) => {
            invalidate();
            setText(e.target.value);
          }}
          placeholder={"date,asset,benchmark\nYYYY-MM-DD,资产复权价,基准复权价"}
        />
      </label>
      <button
        className="button"
        type="button"
        disabled={busy}
        onClick={calculate}
      >
        {busy ? "计算中…" : "计算历史 Beta"}
      </button>
      {error && (
        <p className="r-alert" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="beta-result">
          <strong>Beta {result.data.beta.toFixed(3)}</strong>
          <br />
          R²{" "}
          {result.data.rSquared == null
            ? "—"
            : `${(result.data.rSquared * 100).toFixed(1)}%`}{" "}
          · {result.data.observations} 个收益率
          <br />
          {result.data.start} — {result.data.end}
          <p>
            基准：{result.data.benchmark} · 历史 OLS 估计，不是未来风险预测。
          </p>
          <button
            type="button"
            className="button primary"
            disabled={result.data.beta < 0 || result.data.beta > 5}
            onClick={() => onApply(result.data.beta, result.sample)}
          >
            应用 Beta 到 CAPM
          </button>
          {(result.data.beta < 0 || result.data.beta > 5) && (
            <p>
              结果超出当前 CAPM 工具支持的 0–5 范围；保留估计结果，不强行截断。
            </p>
          )}
        </div>
      )}
    </details>
  );
}
