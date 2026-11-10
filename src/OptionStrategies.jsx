import {customerMessage} from './customer-message';
import {useEffect,useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {OptionsAI,fmt,readJson} from './EvidenceAnswer';
import './quant-research.css';
import LiveStrategies from './LiveStrategies';

const catalog=[
  {id:'long-call',name:'买入看涨',tag:'看涨',view:'看好上涨，承担有限权利金损失。',risk:'方向看对仍可能亏损：时间衰减和隐含波动率回落会压低权利金。',legs:[['call',1,100,6]]},
  {id:'long-put',name:'买入看跌',tag:'看跌',view:'研究下跌情景，最大损失为权利金。',risk:'下跌幅度必须覆盖成本；到期前波动率与时间价值同样重要。',legs:[['put',1,100,5]]},
  {id:'covered-call',name:'备兑看涨',tag:'持股',view:'持有股票并卖出看涨期权，以封顶上涨空间换取权利金。',risk:'股票大幅下跌的风险仍在，可能提前被指派交付股票。',shares:100,legs:[['call',-1,110,3]]},
  {id:'protective-put',name:'保护性看跌',tag:'保护',view:'给持股增加到期下跌保护。',risk:'保护有成本；到期后保护结束，提前行权会影响持仓。',shares:100,legs:[['put',1,90,3]]},
  {id:'bull-call',name:'牛市看涨价差',tag:'看涨',view:'买低执行价 Call、卖高执行价 Call，降低成本并限制收益。',risk:'卖出腿有指派风险，临近到期需关注跨行权价和腿间执行差异。',legs:[['call',1,100,6],['call',-1,110,3]]},
  {id:'bear-put',name:'熊市看跌价差',tag:'看跌',view:'买高执行价 Put、卖低执行价 Put，研究有限幅度下跌。',risk:'收益封顶；方向和跌幅不足仍可损失净权利金。',legs:[['put',1,100,5],['put',-1,90,2]]},
  {id:'bull-put',name:'牛市看跌信用价差',tag:'温和看涨',view:'卖高执行价 Put、买低执行价 Put，收取净权利金。',risk:'下跌超过区间会产生较大损失，收取权利金不等于低风险。',legs:[['put',-1,100,5],['put',1,90,2]]},
  {id:'bear-call',name:'熊市看涨信用价差',tag:'温和看跌',view:'卖低执行价 Call、买高执行价 Call，收益上限为净收入。',risk:'标的大幅上涨不利；需考虑保证金与空头腿提前指派。',legs:[['call',-1,100,6],['call',1,110,3]]},
  {id:'long-straddle',name:'买入跨式',tag:'大幅波动',view:'同到期、同行权价买 Call 与 Put，研究双向大幅波动。',risk:'财报后 IV 回落与时间衰减可能抵消价格变动的收益。',legs:[['call',1,100,6],['put',1,100,5]]},
  {id:'iron-condor',name:'铁鹰',tag:'区间',view:'组合看涨与看跌信用价差，研究到期保持区间的情景。',risk:'跳空可能迅速触及最大损失，临到期指派可打破理想组合。',legs:[['put',1,80,1],['put',-1,90,3],['call',-1,110,3],['call',1,120,1]]},
  {id:'collar',name:'领口策略',tag:'保护',view:'持股、买保护 Put、卖 Call，限定到期盈亏区间。',risk:'上涨受限，买卖腿权利金不同，不保证零成本。',shares:100,legs:[['put',1,90,3],['call',-1,110,3]]}
];
function inputs(s){return {name:s.name,spot:100,stock_shares:s.shares||0,legs:s.legs.map(([side,quantity,strike,premium])=>({side,quantity,strike,premium}))};}
function Payoff({data}){
  const p=data.points,W=800,H=300,L=65,R=25,T=22,B=38,maxX=p.at(-1).price,minY=Math.min(0,...p.map(x=>x.pnl)),maxY=Math.max(0,...p.map(x=>x.pnl));
  const x=v=>L+v/maxX*(W-L-R),y=v=>T+(maxY-v)/Math.max(1,maxY-minY)*(H-T-B);
  return <svg className="payoff-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="策略到期盈亏图，横轴为到期股价，纵轴为美元盈亏"><line x1={L} y1={y(0)} x2={W-R} y2={y(0)} className="payoff-zero"/>{[minY,maxY].map((v,i)=><g key={i}><line x1={L} y1={y(v)} x2={W-R} y2={y(v)} className="payoff-grid"/><text x={L-10} y={y(v)+4} textAnchor="end">{fmt(v,0)}</text></g>)}<path d={p.map((v,i)=>`${i?'L':'M'}${x(v.price)},${y(v.pnl)}`).join(' ')} fill="none" stroke="var(--text)" strokeWidth="3"/>{data.breakEvens.map(v=><g key={v}><circle cx={x(v)} cy={y(0)} r="4" fill="var(--text)"/><text x={x(v)} y={H-13} textAnchor="middle">${fmt(v)}</text></g>)}<text x={L} y={H-13}>$0</text><text x={W-R} y={H-13} textAnchor="end">${fmt(maxX,0)}</text><text x={L} y={14}>盈亏 USD</text><text x={W-R} y={14} textAnchor="end">到期股价 →</text></svg>;
}
function EducationalStrategies({onOptions}){
  const [selected,setSelected]=useState(catalog[0]),[form,setForm]=useState(inputs(catalog[0])),[data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{const ac=new AbortController();setData(null);setError('');const t=setTimeout(()=>{fetch('/api/options/strategy',{method:'POST',signal:ac.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(form)}).then(readJson).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);});},300);return()=>{clearTimeout(t);ac.abort();};},[form]);
  function pick(s){setSelected(s);setForm(inputs(s));}
  function editLeg(index,field,value){setForm(f=>({...f,legs:f.legs.map((l,i)=>i===index?{...l,[field]:Number(value)}:l)}));}
  return <div className="strategies-workspace"><div className="quant-toolbar"><p className="quant-muted">理解策略结构、到期盈亏与风险。所有初始数字均为教学假设，可自行调整。</p><button className="button" onClick={onOptions}>查看真实期权链<ArrowUpRight size={14}/></button></div><div className="strategy-layout"><nav className="strategy-list" aria-label="期权策略">{catalog.map(s=><button key={s.id} className={s.id===selected.id?'selected':''} onClick={()=>pick(s)}><span>{s.name}</span><small>{s.tag}</small></button>)}</nav><div className="strategy-main"><header><span className="eyebrow">OPTIONS PLAYBOOK / {selected.id.toUpperCase()}</span><h2>{selected.name}</h2><p>{selected.view}</p></header><div className="strategy-inputs"><label>标的参考价 / 买入成本<input type="number" min="0.01" max="100000" step="1" aria-label="策略标的价格" value={form.spot} onChange={e=>setForm(f=>({...f,spot:Number(e.target.value)}))}/></label><span>股票持仓：{form.stock_shares} 股 · 编辑后以实际组合腿为准</span></div><div className="quant-table-wrap"><table className="strategy-legs"><thead><tr><th>组合腿</th><th>行权价</th><th>权利金 / 股</th><th>份数</th></tr></thead><tbody>{form.legs.map((l,i)=><tr key={`${selected.id}-${i}`}><td>{l.quantity>0?'买入':'卖出'} {l.side.toUpperCase()}</td><td><input type="number" min="0.01" max="100000" aria-label={`第${i+1}腿行权价`} value={l.strike} onChange={e=>editLeg(i,'strike',e.target.value)}/></td><td><input type="number" min="0" max="100000" step="0.1" aria-label={`第${i+1}腿权利金`} value={l.premium} onChange={e=>editLeg(i,'premium',e.target.value)}/></td><td>1 × 100 股</td></tr>)}</tbody></table></div>{error&&<p role="alert" className="quant-error">{customerMessage(error)}</p>}{data&&<><div className="quant-metrics"><div><span>理论最大收益</span><strong>{data.maxProfit==null?'无上限':'$'+fmt(data.maxProfit)}</strong></div><div><span>理论最大损失</span><strong>{data.maxLoss==null?'无上限':'$'+fmt(data.maxLoss)}</strong></div><div><span>到期盈亏平衡点</span><strong>{data.breakEvens.map(v=>'$'+fmt(v)).join(' / ')||'没有离散交点'}</strong></div></div><Payoff data={data}/><p className="quant-note">{selected.risk}</p><details className="quant-method"><summary>查看计算公式与假设</summary><p>组合盈亏 = 持股数 × (到期价 − 股票成本) + 100 × Σ [买卖方向 × (期权内在价值 − 权利金)]。</p><p>Call 内在价值 = max(S − K, 0)；Put = max(K − S, 0)。最大盈亏由所有行权价拐点及右侧斜率求出，不从图表显示范围估计。</p><p>{data.notice}</p><a href={data.sourceUrl} target="_blank" rel="noreferrer">OIC 期权策略知识库 ↗</a></details><OptionsAI key={data.snapshotId} snapshot={data.snapshotId}/></>}</div></div></div>;
}

export default function OptionStrategies({onOptions,seed}){
  const [mode,setMode]=useState('live');
  return <div><div className="quant-toggle strategy-mode" aria-label="策略数据模式"><button className={mode==='live'?'active':''} onClick={()=>setMode('live')}>真实合约与策略比较</button><button className={mode==='education'?'active':''} onClick={()=>setMode('education')}>教学策略模板</button></div>{mode==='live'?<LiveStrategies onOptions={onOptions} seed={seed}/>:<EducationalStrategies onOptions={()=>setMode('live')}/>}</div>;
}
