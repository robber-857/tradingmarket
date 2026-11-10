import {useId} from 'react';
import './analysis-depth.css';

export default function AnalysisDepth({value,onChange,disabled=false}){
  const id=useId();
  return <div className="analysis-depth"><div role="group" aria-label="分析方式" aria-describedby={id}>
    <button type="button" aria-pressed={value==='standard'} disabled={disabled} onClick={()=>onChange('standard')}>普通解读</button>
    <button type="button" aria-pressed={value==='deep'} disabled={disabled} onClick={()=>onChange('deep')}>深度分析</button>
  </div><small id={id}>{value==='deep'?'检查反例、关键假设与证据缺口 · 成功后扣 1 次深度额度':'提炼当前证据与主要影响 · 成功后扣 1 次 AI 额度'}</small>{value==='deep'&&<small>基于当前数据，耗时更长；不包含额外全网检索。</small>}</div>;
}
