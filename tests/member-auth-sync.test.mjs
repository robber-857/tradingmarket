import {test} from 'node:test';
import assert from 'node:assert/strict';
import {memberRequest} from '../src/member-api.js';
import {getAccountSnapshot, notifyAuthChange, subscribeAuthChange} from '../src/auth-state.js';

test('verification immediately publishes account and delayed anonymous reads cannot undo login',async()=>{
  const originals=Object.getOwnPropertyDescriptors(globalThis);
  const win=new EventTarget(),doc=new EventTarget();doc.visibilityState='visible';
  const writes=[],events=[];
  let resolveOld;
  const user={user:{email:'qa@example.com'},usage:{},plan:'free'};
  const response=data=>({ok:true,status:200,json:async()=>data});
  const queue=[()=>new Promise(resolve=>{resolveOld=resolve;}),()=>Promise.resolve(response(user)),()=>Promise.resolve(response({ok:true}))];
  for(const [key,value] of Object.entries({window:win,document:doc,localStorage:{setItem:(...args)=>writes.push(args)},location:{hash:'#membership'},fetch:()=>queue.shift()()}))
    Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
  const stop=subscribeAuthChange(e=>events.push(e?.account));
  try{
    notifyAuthChange();
    const pending=memberRequest('/api/account');
    await memberRequest('/api/auth/verify',{method:'POST'});
    assert.equal(getAccountSnapshot(),user);
    assert.equal(events.at(-1),user);
    resolveOld(response({user:null}));
    assert.equal(await pending,user);
    await memberRequest('/api/auth/logout',{method:'POST'});
    assert.equal(getAccountSnapshot().user,null);
    assert.equal(events.at(-1).user,null);
    // Initial OAuth document announces once; storage-triggered reads don't echo forever.
    globalThis.fetch=async()=>response(user);
    await memberRequest('/api/account');
    const count=writes.length;
    const event=new Event('storage');event.key='clarora-auth-change';win.dispatchEvent(event);
    await memberRequest('/api/account');
    assert.equal(writes.length,count);
    assert.equal(getAccountSnapshot(),user);
  }finally{
    stop();
    for(const key of ['window','document','localStorage','location','fetch']){
      if(originals[key])Object.defineProperty(globalThis,key,originals[key]);else delete globalThis[key];
    }
  }
});
