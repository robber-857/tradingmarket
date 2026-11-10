import {customerMessage} from './customer-message';
import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,RefreshCw,Search,X} from 'lucide-react';
import {OptionsAI,fmt,readJson} from './EvidenceAnswer';
import './live-strategies.css';

const colors=['#376b4c','#91a44e','#678da2','#a58165'];
const stamp=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Australia/Sydney'});
const price=(row,basis,qty)=>!row||row.bid==null||row.ask==null||row.bid>row.ask||row.ask<=0?null:basis==='mid'?row.mid:qty>0?row.ask:row.bid;

function ComparisonChart({strategies,spot}){
  const W=900,H=340,L=76,R=25,T=24,B=42;
  const [full,setFull]=useState(false);
  const anchors=strategies.flatMap(s=>[...s.legs.map(l=>l.strike),...s.breakEvens]);
  const minX=full?0:Math.max(0,Math.min(spot*.9,...anchors)-spot*.02),maxX=full?Math.max(...strategies.flatMap(s=>s.points.map(p=>p.price))):Math.max(spot*1.1,...anchors)+spot*.02;
  const plotted=strategies.map(s=>({...s,points:[{price:minX,pnl:at(s.points,minX)},...s.points.filter(p=>p.price>minX&&p.price<maxX),{price:maxX,pnl:at(s.points,maxX)}]}));
  const all=plotted.flatMap(s=>s.points),lo=Math.min(0,...all.map(p=>p.pnl)),hi=Math.max(0,...all.map(p=>p.pnl));
  const x=n=>L+(n-minX)/(maxX-minX)*(W-L-R),y=n=>T+(hi-n)/Math.max(1,hi-lo)*(H-T-B);
  const [hover,setHover]=useState(null);
  function at(points,n){let i=points.findIndex(p=>p.price>=n);if(i<0)i=points.length-1;if(!i)return points[0].pnl;const a=points[i-1],b=points[i];return a.pnl+(b.pnl-a.pnl)*(n-a.price)/(b.price-a.price);}
  return <section className="live-payoff"><div className="quant-section-title"><div><span className="eyebrow">EXPIRY PAYOFF COMPARISON</span><h3>同一股价下，比较到期盈亏</h3></div><button className="button" onClick={()=>{setFull(v=>!v);setHover(null);}}>{full?'聚焦行权区间':'展开至零股价'}</button></div><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="真实合约策略到期盈亏比较图" onPointerLeave={()=>setHover(null)} onPointerMove={e=>{const box=e.currentTarget.getBoundingClientRect();setHover(Math.max(minX,Math.min(maxX,minX+((e.clientX-box.left)/box.width*W-L)/(W-L-R)*(maxX-minX))));}}>
    {[lo,0,hi].map((v,i)=><g key={i}><line x1={L} y1={y(v)} x2={W-R} y2={y(v)} className={v===0?'payoff-zero':'payoff-grid'}/><text x={L-10} y={y(v)+4} textAnchor="end">{fmt(v,0)}</text></g>)}
    {plotted.map((s,i)=><path key={s.name} d={s.points.map((p,j)=>`${j?'L':'M'}${x(p.price)},${y(p.pnl)}`).join(' ')} fill="none" stroke={colors[i]} strokeWidth="2.5"/>)}
    {[minX,(minX+maxX)/2,maxX].map(v=><text key={v} x={x(v)} y={H-13} textAnchor="middle">${fmt(v)}</text>)}
    {hover!=null&&<line x1={x(hover)} x2={x(hover)} y1={T} y2={H-B} stroke="#9cae8d" strokeDasharray="3 3"/>}<text x={L} y={14}>盈亏 USD</text><text x={W-R} y={14} textAnchor="end">到期股价 →</text></svg><div className="live-legend">{strategies.map((s,i)=><span key={s.name}><i style={{background:colors[i]}}/>{s.name}{hover!=null&&<b>${fmt(at(s.points,hover))}</b>}</span>)}</div><p className="quant-muted">{hover!=null?`到期股价 $${fmt(hover)} · `:''}曲线只表示显示区间内的到期结果，含输入开仓费；最大盈亏按完整价格范围计算。Greeks 描述报价时点的局部敏感度。</p></section>;
}

export default function LiveStrategies({seed,onOptions}){
  const [query,setQuery]=useState(seed?.symbol||'AAPL'),[suggestions,setSuggestions]=useState([]);
  const [symbol,setSymbol]=useState(seed?.symbol||'AAPL'),[expiry,setExpiry]=useState(seed?.expiry||''),[rate,setRate]=useState((seed?.rate??.04)*100),[dividend,setDividend]=useState((seed?.dividend_yield??0)*100);
  const [chain,setChain]=useState(null),[templates,setTemplates]=useState([]),[scenarios,setScenarios]=useState([]),[active,setActive]=useState('');
  const [basis,setBasis]=useState('natural'),[fee,setFee]=useState(0),[busy,setBusy]=useState(false),[calculating,setCalculating]=useState(false),[result,setResult]=useState(null),[error,setError]=useState(''),[compareError,setCompareError]=useState('');
  const chainCtrl=useRef(null),generation=useRef(0),requestVersion=useRef(0);
  const parameterDirty=chain&&(Number(rate)/100!==chain.assumptions.rate||Number(dividend)/100!==chain.assumptions.dividendYield);
  const payload=chain&&scenarios.length?{chain_snapshot_id:chain.snapshotId,price_basis:basis,fee_per_contract:Number(fee),scenarios:scenarios.map(({id,...s})=>s)}:null;
  const signature=JSON.stringify(payload);
  const currentResult=result?.signature===signature&&!parameterDirty?result.data:null;
  useEffect(()=>{const ac=new AbortController();const token=++generation.current;const timer=setTimeout(async()=>{
    if(query.trim().length<2||query.trim().toUpperCase()===symbol){setSuggestions([]);return;}
    try{const d=await fetch(`/api/research/assets?q=${encodeURIComponent(query.trim())}`,{signal:ac.signal}).then(readJson);if(token===generation.current&&!ac.signal.aborted){const q=query.trim().toLowerCase();setSuggestions(d.results.sort((a,b)=>Number(!(a.symbol.toLowerCase()===q||a.english.toLowerCase().startsWith(q)))-Number(!(b.symbol.toLowerCase()===q||b.english.toLowerCase().startsWith(q)))));}}
    catch(e){if(e.name!=='AbortError')setSuggestions([]);}
  },300);return()=>{clearTimeout(timer);ac.abort();};},[query,symbol]);

  async function load(sym=symbol,exp=expiry){
    chainCtrl.current?.abort();const ac=new AbortController();chainCtrl.current=ac;const token=++requestVersion.current;
    setBusy(true);setError('');setCompareError('');setChain(null);setResult(null);setScenarios([]);setTemplates([]);setSuggestions([]);++generation.current;
    try{
      const get=e=>fetch('/api/options/analyze',{method:'POST',signal:ac.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:sym,expiry:e||null,rate:Number(rate)/100,dividend_yield:Number(dividend)/100})}).then(readJson);
      let c=await get(exp);
      if(!exp){const target=new Date(Date.now()+30*86400000).toISOString().slice(0,10),near=c.expiries.find(e=>e>=target);if(near&&near!==c.expiry)c=await get(near);}
      const t=await fetch(`/api/options/live-templates?snapshot_id=${c.snapshotId}`,{signal:ac.signal}).then(readJson);
      if(ac.signal.aborted||token!==requestVersion.current)return;
      setChain(c);setSymbol(c.symbol);setExpiry(c.expiry);setTemplates(t.templates);
      const picks=t.templates.filter(t=>t.available&&['long-call','bull-call'].includes(t.id)).map(({notice,available,...t})=>t);
      setScenarios(picks);setActive(picks[0]?.id||'');
    }catch(e){if(e.name!=='AbortError')setError(e.message);}finally{if(!ac.signal.aborted)setBusy(false);}
  }
  useEffect(()=>{load(seed?.symbol||'AAPL',seed?.expiry||'');return()=>chainCtrl.current?.abort();},[]);
  useEffect(()=>{setResult(null);setCompareError('');if(!payload||parameterDirty){setCalculating(false);return;}
    const ac=new AbortController();setCalculating(true);const timer=setTimeout(()=>{
      fetch('/api/options/compare',{method:'POST',signal:ac.signal,headers:{'Content-Type':'application/json'},body:signature}).then(readJson).then(d=>{if(!ac.signal.aborted)setResult({signature,data:d});}).catch(e=>{if(e.name!=='AbortError')setCompareError(e.message);}).finally(()=>{if(!ac.signal.aborted)setCalculating(false);});
    },250);return()=>{clearTimeout(timer);ac.abort();};
  },[signature,parameterDirty]);
  function choose(sym){setQuery(sym);setSymbol(sym);setExpiry('');load(sym,'');}
  function pick(t){if(scenarios.some(s=>s.id===t.id)){setActive(t.id);return;}if(scenarios.length>=4){setCompareError('最多同时比较四个组合，请先移除一个。');return;}const {notice,available,...spec}=t;setScenarios(s=>[...s,spec]);setActive(t.id);}
  function editLeg(i,field,value){setScenarios(s=>s.map(s=>s.id===active?{...s,legs:s.legs.map((l,j)=>j===i?{...l,[field]:value}:l)}:s));}
  function remove(id){const remaining=scenarios.filter(s=>s.id!==id);setScenarios(remaining);if(active===id)setActive(remaining[0]?.id||'');}
  const editor=scenarios.find(s=>s.id===active),rows=chain?.contracts||[];
  const selectedResult=currentResult?.strategies.find(s=>s.name===editor?.name);
  return <div className="live-strategies">
    <div className="quant-toolbar"><p className="quant-muted">选择同一股票和到期日的真实合约，最多比较四个建仓情景。</p><button className="button" onClick={()=>onOptions?.({symbol,expiry,rate:Number(rate)/100,dividend_yield:Number(dividend)/100})}>查看期权分布<ArrowUpRight size={14}/></button></div>
    <form className="option-search" onSubmit={e=>{e.preventDefault();const q=query.trim().toLowerCase(),match=suggestions.find(s=>s.symbol.toLowerCase()===q)||suggestions.find(s=>s.english.toLowerCase().startsWith(q)||s.name?.toLowerCase().startsWith(q));choose(match?.symbol||query.trim().toUpperCase());}}><div className="option-search-input"><Search size={17}/><input aria-label="搜索策略股票" value={query} onChange={e=>setQuery(e.target.value)} placeholder="股票代码或英文公司名" autoComplete="off"/>{suggestions.length>0&&<div className="option-suggestions">{suggestions.slice(0,6).map(s=><button type="button" key={s.symbol} onClick={()=>choose(s.symbol)}><b>{s.symbol}</b><span>{s.english}</span></button>)}</div>}</div><button className="button primary" disabled={busy}>{busy?'正在读取…':'读取真实期权链'}</button></form>
    <div className="option-parameters"><label>到期日<select aria-label="策略到期日" value={expiry} disabled={!chain||busy} onChange={e=>{setExpiry(e.target.value);load(symbol,e.target.value);}}>{!chain&&<option value={expiry}>{busy?"正在读取到期日…":"请先选择股票"}</option>}{chain?.expiries.map(e=><option key={e}>{e}</option>)}</select></label><label>利率假设 %<input type="number" min="0" max="25" step="0.1" value={rate} onChange={e=>setRate(e.target.value)}/></label><label>股息率假设 %<input type="number" min="0" max="25" step="0.1" value={dividend} onChange={e=>setDividend(e.target.value)}/></label><button className="button" disabled={busy} onClick={()=>load()}><RefreshCw size={14}/>刷新链与重置组合</button></div>
    {error&&<p className="quant-error" role="alert">{customerMessage(error)}</p>}{busy&&<p className="quant-loading" role="status">正在匹配真实行权价、报价与模型 Greeks…</p>}
    {chain&&<><div className="live-chain-banner"><div><span className="eyebrow">{chain.symbol} / {chain.expiry}</span><strong>${fmt(chain.spot)}<small>来源标的价格</small></strong></div><div><a href={chain.sourceUrl} target="_blank" rel="noreferrer">Nasdaq 期权链 ↗</a><small>{chain.sourceAsOf}</small><small>采集 {stamp(chain.retrievedAt)} 悉尼 · 逐合约报价时间未提供</small></div></div>
      <p className="quant-muted">初次默认选择约一个月后的可用到期日；从期权分析进入时保留到期日。刷新股票或到期日后重新选择合约，避免混用报价。</p>
      <div className="live-basis"><label>建仓报价口径<select aria-label="策略报价口径" value={basis} onChange={e=>setBasis(e.target.value)}><option value="natural">买入 Ask / 卖出 Bid</option><option value="mid">中间价参考</option></select></label><label>开仓费 / 份 / 腿（USD）<input type="number" aria-label="每份期权开仓费" min="0" max="50" step="0.01" value={fee} onChange={e=>setFee(e.target.value)}/></label><p>未将 Last 当作可成交报价。Greeks 使用有效中间价反推 IV，与建仓计价口径分开。</p></div>
      {parameterDirty&&<p className="quant-note">模型假设已修改，请刷新链后重新选择组合。旧计算与 AI 暂不可用。</p>}
      <div className="live-builder"><nav aria-label="真实策略模板"><span className="eyebrow">选择策略加入比较</span>{templates.map(t=><button key={t.id} disabled={!t.available} className={t.id===active?'selected':''} onClick={()=>pick(t)}><span>{t.name}</span><small>{scenarios.some(s=>s.id===t.id)?'已选':t.available?'＋':'缺合约'}</small></button>)}<p className="quant-muted">模板使用 ATM 与相邻档位，仅作为结构起点。编辑合约后以实际组合腿为准。</p></nav>
      <div className="live-editor"><div className="live-selected">{scenarios.map(s=><div key={s.id} className={s.id===active?'active':''}><button onClick={()=>setActive(s.id)}>{s.name}</button><button aria-label={`移除${s.name}`} onClick={()=>remove(s.id)}><X size={12}/></button></div>)}</div>
      {editor?<><div className="quant-section-title"><div><span className="eyebrow">CONTRACT BUILDER</span><h2>{editor.name}</h2></div><label>股票持仓<select aria-label="组合股票持仓" value={editor.stock_shares} onChange={e=>setScenarios(all=>all.map(s=>s.id===active?{...s,stock_shares:Number(e.target.value)}:s))}><option value={0}>不含股票</option><option value={100}>100 股 · 以来源价建仓</option></select></label></div>
      <div className="quant-table-wrap"><table className="live-legs"><thead><tr><th>买卖 / 份数</th><th>真实合约</th><th>Bid / Ask</th><th>带入价格 / 股</th><th>价差 / IV</th></tr></thead><tbody>{editor.legs.map((l,i)=>{const row=rows.find(r=>r.id===l.contract_id);return <tr key={i}><td><select aria-label={`第${i+1}腿买卖方向`} value={Math.sign(l.quantity)} onChange={e=>editLeg(i,'quantity',Number(e.target.value)*Math.abs(l.quantity))}><option value={1}>买入</option><option value={-1}>卖出</option></select><input aria-label={`第${i+1}腿合约份数`} type="number" min="1" max="10" value={Math.abs(l.quantity)} onChange={e=>editLeg(i,'quantity',Math.sign(l.quantity)*Number(e.target.value))}/></td><td><select aria-label={`第${i+1}腿真实合约`} value={l.contract_id} onChange={e=>editLeg(i,'contract_id',e.target.value)}>{rows.map(r=><option key={r.id} value={r.id}>{r.side.toUpperCase()} ${fmt(r.strike)}{price(r,basis,l.quantity)==null?' · 报价不足':''}</option>)}</select><small>{chain.expiry} · 标准 100 股</small></td><td>{fmt(row?.bid)} / {fmt(row?.ask)}<small>OI {fmt(row?.oi,0)} · Vol {fmt(row?.volume,0)}</small></td><td><b>{price(row,basis,l.quantity)==null?'不可用':'$'+fmt(price(row,basis,l.quantity),4)}</b><small>{basis==='mid'?'MID':l.quantity>0?'ASK':'BID'}</small></td><td>{fmt(row?.spreadPct)}%<small>IV {row?.iv==null?'缺失':fmt(row.iv*100)+'%'}</small></td></tr>;})}</tbody></table></div>
      <p className="quant-muted">合约价格取自同一份期权链数据；各合约实际报价时间可能不同；编辑份数、报价口径或费用会重新计算并重置之前的 AI 解读。每次最多四条腿。</p>
      {selectedResult&&<div className="live-risk"><b>当前组合风险</b>{selectedResult.riskNotes.map(r=><p key={r}>{r}</p>)}</div>}</>:<p className="quant-note">从左侧选择策略开始比较。</p>}
      </div></div>
      {compareError&&<p role="alert" className="quant-error">{compareError}</p>}{calculating&&<p className="quant-muted" role="status">正在按当前合约重新计算…</p>}
      {currentResult&&<><section className="live-comparison"><div className="quant-section-title"><div><span className="eyebrow">SIDE BY SIDE</span><h3>成本、盈亏与组合 Greeks</h3></div><span className="quant-muted">{basis==='natural'?'买 Ask / 卖 Bid':'中间价参考'} · {scenarios.length} 个情景</span></div><div className="quant-table-wrap"><table><thead><tr><th>比较指标</th>{currentResult.strategies.map((s,i)=><th key={s.name}><i style={{background:colors[i]}} className="live-dot"/>{s.name}</th>)}</tr></thead><tbody>{[
          ['净开仓支出（含股票 / 费用）',s=>'$'+fmt(s.netDebit)],['期权净支出（负数为收入）',s=>'$'+fmt(s.optionDebit)],['开仓费用',s=>'$'+fmt(s.fees)],
          ['理论最大收益',s=>s.maxProfit==null?'无上限':'$'+fmt(s.maxProfit)],['理论最大损失',s=>s.maxLoss==null?'无上限':'$'+fmt(s.maxLoss)],['到期盈亏平衡点',s=>s.breakEvens.map(v=>'$'+fmt(v)).join(' / ')||'无离散交点'],
          ['Delta · 股等效',s=>fmt(s.greeks.delta,3)],['Gamma · 股等效 / USD',s=>fmt(s.greeks.gamma,4)],['Theta · USD / 天',s=>fmt(s.greeks.theta,3)],['Vega · USD / 波动率百分点',s=>fmt(s.greeks.vega,3)],['Rho · USD / 利率百分点',s=>fmt(s.greeks.rho,3)],
          ['Greeks 覆盖',s=>s.greekCoverage.complete?'全部合约可计算':`${s.greekCoverage.pricedLegs}/${s.greekCoverage.totalLegs} 腿 · 组合不完整`],['全组合买卖价差总额',s=>'$'+fmt(s.spreadCost)]
        ].map(([label,get])=><tr key={label}><th>{label}</th>{currentResult.strategies.map(s=><td key={s.name}>{get(s)}</td>)}</tr>)}</tbody></table></div><p className="quant-muted">净支出不是保证金；不同份数与持股资本不能直接比较资金收益率。任何一腿缺少 Greeks，整组显示 —，不把缺失当零。</p></section>
        <ComparisonChart strategies={currentResult.strategies} spot={currentResult.spot}/><OptionsAI key={currentResult.snapshotId} snapshot={currentResult.snapshotId}/><details className="quant-method"><summary>公式、数据时间与比较口径</summary><p>Π(S) = 持股数 × (S − 来源股价) + 100 × Σ[有方向份数 × (内在价值 − 建仓参考价)] − 输入开仓费。</p><p>Delta = 持股数 + 100 × Σ(有方向份数 × 单腿 Delta)。其余 Greeks = 100 × Σ(有方向份数 × 单腿 Greeks)。所有腿来自同一股票、到期日与本次取得的期权链数据；不保证各合约报价同时更新。</p><p>{currentResult.notice}</p><p>Greeks 链计算时点：{stamp(currentResult.chainCalculatedAt)} 悉尼。BSM 为欧式近似，离散股息与实际提前指派未建模。</p><a href="https://www.optionseducation.org/advancedconcepts/understanding-options-greeks" target="_blank" rel="noreferrer">OIC Greeks 说明 ↗</a></details></>}
    </>}
  </div>;
}
