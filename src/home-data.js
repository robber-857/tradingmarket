// Homepage selection is deterministic; no model-generated ranking or fabricated market data.
export const categoryNames = {all:'全部市场',stocks:'美股',crypto:'加密货币',macro:'宏观'};
export const zoneNames = {'America/New_York':'美东','Asia/Shanghai':'北京','Australia/Sydney':'悉尼'};
export function dayKey(value,zone='Australia/Sydney') {
  return new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
}
export function recentNews(items=[],category='all',now=Date.now()) {
  return items.filter(a=>{const age=now-Date.parse(a.publishedAt);return Number.isFinite(age)&&age>=0&&age<=86400000&&(category==='all'||a.categories?.includes(category));})
    .sort((a,b)=>Number(!!a.stale)-Number(!!b.stale)||Date.parse(b.publishedAt)-Date.parse(a.publishedAt));
}
export function newsSelection(items,category='all',now=Date.now(),limit=6) {
  const list=recentNews(items,category,now);
  if(category!=='all')return list.slice(0,limit);
  const picks=[];
  for(const tag of ['stocks','crypto','macro']){const item=list.find(a=>a.categories?.includes(tag)&&!picks.some(p=>p.id===a.id));if(item)picks.push(item);}
  return [...picks,...list.filter(a=>!picks.some(p=>p.id===a.id))].slice(0,limit);
}
export function latestReady(index) {
  return [...(index?.editions||[])].filter(e=>e.status==='ready').sort((a,b)=>b.day.localeCompare(a.day))[0]||null;
}
export function eventState(event,now=Date.now()) {
  if(!event.releaseAt||!Number.isFinite(Date.parse(event.releaseAt)))return 'unknown';
  const future=event.timePrecision==='date-only'?dayKey(event.releaseAt,'America/New_York')>dayKey(now,'America/New_York'):Date.parse(event.releaseAt)>now;
  if(future)return 'upcoming';
  if(event.actual)return 'released';
  if(event.timePrecision==='date-only'&&dayKey(event.releaseAt,'America/New_York')===dayKey(now,'America/New_York'))return 'date-only';
  return 'pending';
}
export function agenda(events=[],now=Date.now()) {
  const grouped=new Map();
  const sorted=[...events].filter(e=>e.releaseAt&&Number.isFinite(Date.parse(e.releaseAt))).sort((a,b)=>Date.parse(a.releaseAt)-Date.parse(b.releaseAt)||Number(a.title.includes('核心'))-Number(b.title.includes('核心')));
  for(const e of sorted){const key=e.group+'|'+e.releaseAt;if(!grouped.has(key))grouped.set(key,{...e,displayStatus:eventState(e,now)});}
  const rows=[...grouped.values()];
  const upcoming=rows.filter(e=>['upcoming','date-only'].includes(e.displayStatus));
  const sevenDays=upcoming.filter(e=>e.timePrecision!=='estimated' && (e.timePrecision==='date-only'?dayKey(e.releaseAt,'America/New_York')<=dayKey(now+7*86400000,'America/New_York'):Date.parse(e.releaseAt)<=now+7*86400000));
  const recent=rows.filter(e=>['pending','released'].includes(e.displayStatus)&&now-Date.parse(e.releaseAt)<=2*86400000).reverse();
  return {upcoming,sevenDays,recent,visible:[...recent.filter(e=>e.displayStatus==='pending'),...upcoming,...recent.filter(e=>e.displayStatus==='released')]};
}
export function releaseLabel(event,zone) {
  if(!event.releaseAt)return '发布时间待核验';
  const dateOnly=event.timePrecision==='date-only';
  return new Intl.DateTimeFormat('zh-CN',{timeZone:dateOnly?'America/New_York':zone,month:'2-digit',day:'2-digit',...(!dateOnly&&{hour:'2-digit',minute:'2-digit',hour12:false})}).format(new Date(event.releaseAt))+
    (dateOnly?' 美东 · 时刻待确认':` ${zoneNames[zone]||zone}${event.timePrecision==='estimated'?' · 暂定':''}`);
}

export function sevenDayEvents(events=[],now=Date.now()) {
  const keys=new Set(agenda(events,now).sevenDays.map(e=>e.group+"|"+e.releaseAt));
  return events.filter(e=>e.timePrecision!=="estimated" && keys.has(e.group+"|"+e.releaseAt));
}
