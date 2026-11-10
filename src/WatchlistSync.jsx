import {useState} from 'react';
import {memberRequest} from './member-api';

export default function WatchlistSync({watch,onRestore}) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  async function sync(direction){
    setBusy(true);setMessage('');
    try{
      if(direction==='save'){
        await memberRequest('/api/account/saved/watchlist',{method:'PUT',body:JSON.stringify({kind:'watchlist',title:'我的关注',payload:{symbols:watch}})});
        setMessage('关注清单已保存到账户，可在其他设备读取。');
      }else{
        const data=await memberRequest('/api/account/saved');
        const row=data.items.find(i=>i.id==='watchlist'&&i.kind==='watchlist');
        if(!row){setMessage('账户还没有保存关注清单。');return;}
        const list=row.payload.symbols;
        if(!Array.isArray(list)||list.some(s=>typeof s!=='string'||s.length>25))throw new Error('账户关注清单格式无效。');
        if(window.confirm('用账户保存的关注清单替换当前浏览器清单？')){onRestore(list);setMessage('已读取账户关注清单。');}
      }
    }catch(e){setMessage(e.message);}finally{setBusy(false);}
  }
  return <section className="panel" style={{padding:20,marginBottom:20}}><h3>账户关注清单</h3><p className="fine-print">登录后可保存与跨设备读取。当前浏览器清单不会自动覆盖到账户。</p><button className="button" disabled={busy} onClick={()=>sync('save')}>保存到账户</button> <button className="button" disabled={busy} onClick={()=>sync('load')}>读取账户清单</button>{message&&<p role="status">{message}</p>}</section>;
}
