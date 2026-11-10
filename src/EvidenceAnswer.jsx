import {customerMessage} from './customer-message';
import AnalysisDepth from './AnalysisDepth';
import { useEffect, useRef, useState } from 'react';
import { Sparkles, ArrowUpRight, Send } from 'lucide-react';

export async function readJson(response) {
  const b = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof b.detail === 'string' ? b.detail : '请求未完成，请检查参数后重试。');
  return b;
}
export const fmt = (n, digits=2) => n == null ? '—' : Number(n).toLocaleString('en-US', {maximumFractionDigits:digits});
export function Answer({ result }) {
  const types = {fact:'来源陈述',inference:'研究判断',hypothesis:'条件情景'};
  return <div className="evidence-answer">{result.generationNotice&&<p className="quant-muted" role="status">{result.generationNotice}</p>}{[result.answer.conclusion,...result.answer.insights].map((c,i)=><section key={i} className={i===0?'evidence-lead':''}><span className="eyebrow">{types[c.kind]}</span><p>{c.text}</p><div className="evidence-links">{c.citations.filter(id=>id.startsWith('S_')).map(id=><a key={id} title={result.citations[id]?.display} href={result.citations[id]?.sourceUrl} target="_blank" rel="noreferrer">{result.citations[id]?.label}<ArrowUpRight size={12}/></a>)}</div></section>)}<div className="evidence-watch"><b>下一步关注与风险</b><p>{result.answer.watch_next}</p><small>{result.answer.limitations}</small></div></div>;
}
export function OptionsAI({snapshot}) {
  const [analysisDepth,setAnalysisDepth]=useState('standard');
  const [turns,setTurns]=useState([]),[question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const ctrl=useRef(null);
  useEffect(()=>()=>ctrl.current?.abort(),[]);
  async function ask(q='') {
    if(busy)return;
    const ac=new AbortController();ctrl.current=ac;setBusy(true);setError('');
    try {
      const r=await fetch('/api/options/explain',{method:'POST',signal:ac.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({analysis_depth:analysisDepth,snapshot_id:snapshot,question:q,conversation_id:turns.at(-1)?.conversationId||null})}).then(readJson);
      if(!ac.signal.aborted){setTurns(t=>[...t,r]);setQuestion('');}
    }catch(e){if(e.name!=='AbortError')setError(e.message);}finally{if(!ac.signal.aborted)setBusy(false);}
  }
  return <section className="quant-ai"><h3><Sparkles size={17}/> AI 研究解读</h3><AnalysisDepth value={analysisDepth} onChange={setAnalysisDepth} disabled={busy}/><p className="quant-muted">结合当前到期日与计算参数，解释重点、风险和数据缺口。</p>{!turns.length&&<button className="button primary" disabled={busy} onClick={()=>ask()}>{busy?'正在核对证据…':analysisDepth==='deep'?'生成深度分析':'生成 AI 解读'}</button>}{turns.map((t,i)=><div key={i}>{i>0&&<p className="quant-question">{t.question}</p>}<Answer result={t}/></div>)}{error&&<p role="alert" className="quant-error">{customerMessage(error)}</p>}{!!turns.length&&<><div className="quant-followups">{turns.at(-1).answer.followups.map(q=><button key={q} disabled={busy||turns.length>=8} onClick={()=>ask(q)}>{q}</button>)}</div><form className="quant-ask" onSubmit={e=>{e.preventDefault();if(question.trim())ask(question);}}><input aria-label="期权 AI 追问" placeholder="追问当前计算与风险…" maxLength={1200} value={question} onChange={e=>setQuestion(e.target.value)} disabled={busy||turns.length>=8}/><button className="button" aria-label="发送期权追问" disabled={busy||!question.trim()||turns.length>=8}><Send size={16}/></button></form>{busy&&<p role="status">正在分析…</p>}<button className="quant-text-button" disabled={busy} onClick={()=>{setTurns([]);setError('');}}>开始新解读</button></>}</section>;
}
