import {customerMessage} from './customer-message';
import AnalysisDepth from './AnalysisDepth';
import { useEffect, useRef, useState } from "react";
import {
  Sparkles,
  ArrowUpRight,
  Send,
  RotateCcw,
  Download,
  RefreshCw,
} from "lucide-react";
import "./ai-research.css";

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error("研究服务暂时无法连接，请稍后重试。");
  }
  if (!response.ok) {
    const error = new Error(
      typeof body.detail === "string"
        ? body.detail
        : "请求参数不完整，请检查当前财报与假设。",
    );
    error.status = response.status;
    throw error;
  }
  return body;
}

export default function AIResearch({
  report,
  quarter,
  mode,
  assumptions = null,
  capitalEvidence = null,
  marketSnapshotId = null,
  prompt = null,
  available = true,
  onInspect,
}) {
  const [config, setConfig] = useState(null);
  const [checking, setChecking] = useState(false);
  const [turns, setTurns] = useState([]);
  const [analysisDepth, setAnalysisDepth] = useState('standard');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [needsReset, setNeedsReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const controller = useRef(null);
  const input = useRef(null);
  const alive = useRef(true);
  const sequence = useRef(0);
  const contextKey = JSON.stringify([
    report.snapshotId,
    quarter.end,
    mode,
    assumptions,
    capitalEvidence,
    marketSnapshotId,
  ]);
  const currentContext = useRef(contextKey);
  currentContext.current = contextKey;
  const check = async () => {
    setChecking(true);
    try {
      const data = await jsonRequest("/api/ai/status");
      if (alive.current) {
        setConfig(data);
        setError("");
      }
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setChecking(false);
    }
  };
  useEffect(() => {
    alive.current = true;
    check();
    return () => {
      alive.current = false;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    sequence.current++;
    controller.current?.abort();
    setTurns([]);
    setQuestion("");
    setBusy(false);
    setError("");
    setNeedsReset(false);
  }, [contextKey]);
  useEffect(() => {
    if (prompt) {
      setQuestion(prompt.text);
      input.current?.focus({ preventScroll: true });
    }
  }, [prompt]);
  const ask = async (text = question) => {
    if (busy || !config?.configured || needsReset || !available) return;
    const version = ++sequence.current;
    const sentContext = contextKey;
    const c = new AbortController();
    controller.current = c;
    setBusy(true);
    setError("");
    try {
      const reply = await jsonRequest(
        `/api/research/${report.symbol}/explain`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
          signal: c.signal,
          body: JSON.stringify({
            snapshot_id: report.snapshotId,
            analysis_depth: analysisDepth,
            report_end: quarter.end,
            mode,
            assumptions,
            capital_inputs: capitalEvidence?.inputs || null,
            beta_sample: capitalEvidence?.betaSample || null,
            market_snapshot_id: marketSnapshotId,
            question: text.trim(),
            conversation_id: turns.at(-1)?.conversationId || null,
          }),
        },
      );
      if (
        version !== sequence.current ||
        sentContext !== currentContext.current ||
        !alive.current
      )
        return;
      setTurns((previous) => [...previous, reply]);
      setQuestion("");
    } catch (e) {
      if (
        e.name !== "AbortError" &&
        version === sequence.current &&
        alive.current
      ) {
        setError(e.message);
        setNeedsReset(e.status === 409);
      }
    } finally {
      if (version === sequence.current && alive.current) setBusy(false);
    }
  };
  const reset = () => {
    controller.current?.abort();
    sequence.current++;
    setTurns([]);
    setQuestion("");
    setBusy(false);
    setError("");
    setNeedsReset(false);
  };
  const inspect = (citation) =>
    onInspect({
      title: `${citation.label} · ${citation.period}`,
      kind:
        citation.unit === "price"
          ? "price"
          : citation.unit === "number"
            ? "number"
          : citation.unit === "percent"
            ? "percent"
            : citation.unit === "multiple"
              ? "multiple"
              : citation.unit === "pp"
                ? "pp"
                : citation.unit === "shares"
                  ? "shares"
                  : undefined,
      data: {
        value: citation.value,
        formula:
          citation.formula ||
          (citation.kind === "hypothesis"
            ? "当前用户假设或条件模型输出，非官方预测"
            : "官方财报数据"),
        reason: citation.reason,
        warning: citation.warning,
        evidence: citation.evidence,
        sourceUrl: citation.sourceUrl,
        retrievedAt: citation.retrievedAt,
      },
    });
  const exportTurns = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            symbol: report.symbol,
            reportEnd: quarter.end,
            snapshotId: report.snapshotId,
            turns,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.symbol}-${quarter.end}-ai-research.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const saveResearch = async () => {
    setSaving(true);setSaveMessage('');
    try {
      await jsonRequest('/api/account/saved/'+crypto.randomUUID(), {
        method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kind:'research',title:`${report.symbol} · ${quarter.end} · ${mode==='financials'?'财报':'估值'}研究`,
          payload:{symbol:report.symbol,reportEnd:quarter.end,snapshotId:report.snapshotId,assumptions,analysisDepth,turns,savedAt:new Date().toISOString()}}),
      });
      setSaveMessage('已保存到账户，可在会员中心查看历史研究。');
    } catch(e){setSaveMessage(e.message);}finally{setSaving(false);}
  };
  const claim = (item, turn, lead = false) => (
    <div className={`ai-claim ${lead ? "ai-conclusion" : ""}`}>
      <span className={`ai-kind ${item.kind}`}>
        {
          { fact: "数据事实", inference: "AI 推论", hypothesis: "条件假设" }[
            item.kind
          ]
        }
      </span>
      <p>{item.text}</p>
      <div className="ai-citations">
        {item.citations.map((id) => {
          const c = turn.citations[id];
          return (
            <button
              key={id}
              onClick={() => inspect(c)}
              title={`${c.period} · 查看计算与出处`}
            >
              {c.label} <b>{c.display}</b>
              <ArrowUpRight size={11} />
            </button>
          );
        })}
      </div>
    </div>
  );
  return (
    <section
      className="ai-research"
      id="research-ai"
      aria-labelledby="ai-title"
    >
      <div className="ai-heading">
        <div>
          <span className="eyebrow">EVIDENCE → INSIGHT</span>
          <h2 id="ai-title">
            <Sparkles size={18} />
            AI 解读与追问
          </h2>
          <p>
            {report.symbol} · {quarter.end} ·{" "}
            {mode === "financials" ? "财报证据" : assumptions ? "财报、行情与当前估值假设" : "财报与行情 · 当前无有效 DCF"}
          </p>
        </div>
        <div className="ai-controls">
          <AnalysisDepth value={analysisDepth} disabled={busy} onChange={setAnalysisDepth}/>
          <div className="ai-actions">
          <button className="button" disabled={!turns.length||saving||busy} onClick={saveResearch}>{saving?'保存中…':'保存研究'}</button>
          <span className="badge">
            {config?.configured ? "AI 解读已就绪" : "AI 解读暂不可用"}
          </span>
          {saveMessage&&<span role="status" className="fine-print">{saveMessage}</span>}
          <button
            className="icon-button"
            onClick={check}
            disabled={checking}
            aria-label="检查 AI 服务状态"
          >
            <RefreshCw size={15} />
          </button>
          {turns.length > 0 && (
            <>
              <button
                className="icon-button"
                onClick={exportTurns}
                aria-label="导出 AI 研究"
              >
                <Download size={15} />
              </button>
              <button
                className="icon-button"
                onClick={reset}
                disabled={busy}
                aria-label="开始新解读"
              >
                <RotateCcw size={15} />
              </button>
            </>
          )}
          </div>
        </div>
      </div>
      {!config?.configured && (
        <div className="ai-setup">
          <strong>AI 解读暂不可用</strong>
          <p>
            你仍可查看财报数据与计算结果。请稍后重试，或联系服务支持。
          </p>
        </div>
      )}
      {turns.length === 0 && (
        <div className="ai-start">
          <p>
            {available
              ? "提炼关键变化，说明依据和缺口。点击引用，回到原始数据。"
              : "请先补齐有效估值参数，完成计算后再解读。"}
          </p>
          <button
            className="button primary"
            disabled={!config?.configured || busy || !available}
            onClick={() => ask("")}
          >
            <Sparkles size={15} />
            {busy ? "正在核对证据…" : analysisDepth === "deep" ? "生成深度分析" : "生成简洁解读"}
          </button>
        </div>
      )}
      <div className="ai-turns" aria-live="polite" aria-busy={busy}>
        {turns.map((turn, i) => (
          <article key={`${turn.conversationId}-${turn.turn}`}>
            <div className="ai-turn-heading">
              <span>{i === 0 ? "核心解读" : `追问 ${i}`}</span>
              <small>
                {new Date(turn.generatedAt).toLocaleTimeString("zh-CN", {
                  timeZone: "Australia/Sydney",
                  hour: "2-digit",
                  minute: "2-digit",
                })}{" "}
                · 悉尼
              </small>
            </div>
            {i > 0 && <p className="ai-question">{turn.question}</p>}
            {claim(turn.answer.conclusion, turn, true)}
            <div className="ai-insights">
              {turn.answer.insights.map((item, n) => (
                <div key={n}>{claim(item, turn)}</div>
              ))}
            </div>
            <div className="ai-next">
              <strong>继续验证</strong>
              <p>{turn.answer.watch_next}</p>
              <small>{turn.answer.limitations}</small>
            </div>
          </article>
        ))}
      </div>
      {busy && (
        <p className="ai-progress" role="status">
          <RefreshCw size={14} />
          正在结合数据生成解读，通常需要片刻…
        </p>
      )}
      {error && (
        <div className="r-alert" role="alert">
          {customerMessage(error)}
          {needsReset && (
            <button className="button" onClick={reset}>
              开始新解读
            </button>
          )}
        </div>
      )}
      <div className="ai-followups">
        {(
          turns.at(-1)?.answer.followups ||
          (mode === "financials"
            ? ["利润和现金流有什么分歧？", "股数变化对每股结果意味着什么？"]
            : assumptions ? ["估值最依赖哪项假设？", "P/E、P/B、P/S 应该如何一起看？"] : ["当前可得数据里最值得关注什么？", "哪些数据缺口限制了公司估值？"])
        ).map((q) => (
          <button
            key={q}
            disabled={busy}
            onClick={() => {
              setQuestion(q);
              input.current?.focus({ preventScroll: true });
            }}
          >
            {q}
            <ArrowUpRight size={12} />
          </button>
        ))}
      </div>
      <form
        className="ai-composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) ask();
        }}
      >
        <label htmlFor={`ai-question-${mode}`} className="sr-only">
          追问当前研究
        </label>
        <textarea
          id={`ai-question-${mode}`}
          ref={input}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="围绕当前公司和报告期追问…"
          maxLength={1200}
          rows={2}
          disabled={busy}
        />
        <button
          className="button primary"
          type="submit"
          disabled={
            busy ||
            !config?.configured ||
            !question.trim() ||
            needsReset ||
            turns.length >= 8 ||
            !available
          }
          aria-label="发送研究追问"
        >
          <Send size={16} />
          <span>发送</span>
        </button>
      </form>
      <p className="ai-note">
        只在点击后调用
        OpenAI；会发送当前财报指标、假设与问题。切换公司、季度或假设会重置会话。引用与数值经过校验，AI
        推论仍需复核。
      </p>
    </section>
  );
}
