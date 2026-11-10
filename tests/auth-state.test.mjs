import {test} from 'node:test';
import assert from 'node:assert/strict';
import {notifyAuthChange, subscribeAuthChange} from '../src/auth-state.js';

test('session changes, returning to a tab and cross-tab changes refresh consumers; cleanup removes listeners',()=>{
  const win=new EventTarget(), doc=new EventTarget();
  doc.visibilityState='visible';
  const writes=[];
  const originals=Object.getOwnPropertyDescriptors(globalThis);
  for(const [key,value] of Object.entries({window:win,document:doc,localStorage:{setItem:(...args)=>writes.push(args)}}))
    Object.defineProperty(globalThis,key,{configurable:true,value});
  try{
    let calls=0;
    const stop=subscribeAuthChange(()=>calls++);
    notifyAuthChange();
    assert.equal(calls,1);
    assert.equal(writes[0][0],'clarora-auth-change');
    for(const name of ['focus','pageshow'])win.dispatchEvent(new Event(name));
    doc.dispatchEvent(new Event('visibilitychange'));
    doc.visibilityState='hidden';
    doc.dispatchEvent(new Event('visibilitychange'));
    assert.equal(calls,4);
    const storage=new Event('storage');storage.key='unrelated';win.dispatchEvent(storage);
    storage.key='clarora-auth-change';win.dispatchEvent(storage);
    assert.equal(calls,5);
    stop();notifyAuthChange();win.dispatchEvent(new Event('focus'));win.dispatchEvent(storage);
    assert.equal(calls,5);
    // Storage restrictions must not prevent same-tab updates or successful login.
    localStorage.setItem=()=>{throw new Error('blocked');};
    assert.doesNotThrow(notifyAuthChange);
  }finally{
    for(const key of ['window','document','localStorage']){
      if(originals[key])Object.defineProperty(globalThis,key,originals[key]);else delete globalThis[key];
    }
  }
});
