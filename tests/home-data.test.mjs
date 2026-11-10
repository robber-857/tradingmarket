import {test} from 'node:test';
import assert from 'node:assert/strict';
import {agenda,sevenDayEvents,dayKey,eventState,latestReady,newsSelection,recentNews,releaseLabel} from '../src/home-data.js';

const now=Date.parse('2026-11-10T00:00:00Z');
const article=(id,age,categories=['stocks'],stale=false)=>({id,publishedAt:new Date(now-age*3600000).toISOString(),categories,stale});
const event=(id,releaseAt,more={})=>({id,releaseAt,title:'CPI 同比',group:'CPI',timePrecision:'confirmed',actual:null,...more});

test('recent news excludes future, invalid and older-than-24h articles; freshness is explicit',()=>{
  const rows=[article('future',-1),article('old',25),article('boundary',24),article('fresh',2),article('stale',1,['stocks'],true),{id:'invalid',publishedAt:'bad'}];
  assert.deepEqual(recentNews(rows,'all',now).map(a=>a.id),['fresh','boundary','stale']);
  assert.equal(recentNews(rows,'crypto',now).length,0);
});
test('mixed topic coverage avoids duplicating cross-listed articles and caps list length',()=>{
  const rows=[article('cross',1,['stocks','crypto']),article('coin',2,['crypto']),article('macro',3,['macro']),...Array.from({length:8},(_,i)=>article('s'+i,i+4))];
  const chosen=newsSelection(rows,'all',now);
  assert.deepEqual(chosen.slice(0,3).map(a=>a.id),['cross','coin','macro']);
  assert.equal(chosen.length,6);assert.equal(new Set(chosen.map(a=>a.id)).size,6);
});
test('dashboard pagination can access all news without losing topic diversity',()=>{
  const rows=Array.from({length:20},(_,i)=>article('s'+i,i+1));
  const chosen=newsSelection(rows,'all',now,Infinity);
  assert.equal(chosen.length,20);
  assert.equal(new Set(chosen.map(a=>a.id)).size,20);
});
test('agenda retains all events for paging',()=>{
  const rows=Array.from({length:8},(_,i)=>event('e'+i,`2026-11-${String(i+11).padStart(2,'0')}T13:30:00Z`));
  assert.equal(agenda(rows,now).visible.length,8);
});
test('brief selects latest completed edition, never failed or generating edition',()=>{
  assert.equal(latestReady({editions:[{day:'2026-11-10',status:'failed'},{day:'2026-11-08',status:'ready'},{day:'2026-11-09',status:'ready'},{day:'2026-11-11',status:'generating'}]}).day,'2026-11-09');
  assert.equal(latestReady({editions:[]}),null);
});
test('Sydney edition date and New York viewing date stay independent',()=>{
  assert.equal(dayKey(now,'Australia/Sydney'),'2026-11-10');assert.equal(dayKey(now,'America/New_York'),'2026-11-09');
});
test('past unreleased events become pending even when server status is old',()=>{
  assert.equal(eventState(event('pending','2026-11-09T13:30:00Z',{status:'upcoming'}),now),'pending');
  assert.equal(eventState(event('released','2026-11-09T13:30:00Z',{actual:{display:'3%'}}),now),'released');
  assert.equal(eventState(event('future','2026-11-11T13:30:00Z',{actual:{display:'invalid future actual'}}),now),'upcoming');
  assert.equal(eventState(event('bad',null),now),'unknown');
});
test('date-only event uses New York date and never fabricates a precise time',()=>{
  const e=event('day','2026-11-09T05:00:00Z',{timePrecision:'date-only'});
  assert.equal(eventState(e,now),'date-only');
  assert.match(releaseLabel(e,'Australia/Sydney'),/11\/09 美东 · 时刻待确认/);
  assert.equal(eventState(e,Date.parse('2026-11-10T05:01:00Z')),'pending');
});
test('agenda groups core and headline at same release, counts only next seven days',()=>{
  const rows=[event('core','2026-11-12T13:30:00Z',{title:'核心 CPI'}),event('headline','2026-11-12T13:30:00Z'),event('far','2026-12-11T13:30:00Z',{group:'PCE'}),event('ancient','2026-10-01T12:30:00Z')];
  const result=agenda(rows,now);
  assert.equal(result.sevenDays.length,1);assert.equal(result.visible.length,2);assert.equal(result.visible[0].id,'headline');
});
test('recent missing release stays visible ahead of future events; ancient pending omitted',()=>{
  const rows=[event('pending','2026-11-09T13:30:00Z'),event('future','2026-11-12T13:30:00Z'),event('old','2026-11-01T13:30:00Z')];
  assert.deepEqual(agenda(rows,now).visible.map(e=>e.id),['pending','future']);
  assert.deepEqual(agenda([],now).visible,[]);
});

test('seven-day destination retains all indicators and excludes estimated, past and beyond boundary',()=>{
  const end=new Date(now+7*86400000).toISOString();
  const rows=[event('headline',end),event('core',end,{title:'核心 CPI'}),event('estimated','2026-11-11T13:30:00Z',{timePrecision:'estimated'}),event('past','2026-11-08T13:30:00Z'),event('late',new Date(now+7*86400000+1).toISOString())];
  assert.equal(agenda(rows,now).sevenDays.length,1);
  assert.deepEqual(sevenDayEvents(rows,now).map(e=>e.id),['headline','core']);
});
