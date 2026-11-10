import {useEffect,useState} from 'react';
import {memberRequest} from './member-api';

export default function Academy({localCourses=[],completed=[],onComplete}){
  const [courses,setCourses]=useState([]),[lesson,setLesson]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{memberRequest('/api/academy/courses').then(d=>setCourses(d.courses)).catch(e=>setError(e.message));},[]);
  async function open(id){setBusy(true);setError('');try{setLesson(await memberRequest('/api/academy/courses/'+encodeURIComponent(id)));}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="membership-page"><section className="panel"><span className="eyebrow">CLARORA ACADEMY</span><h2>建立框架，让信息成为认知。</h2><p>免费课开放阅读，会员课由高级会员和专家会员在有效期内解锁。</p><p className="fine-print">现有入门样课继续免费；完整会员课程正在准备，未上线内容不会作为已交付课程售卖。</p><a className="button" href="#membership">查看会员权益</a></section>{error&&<p role="alert" className="home-error">{error}</p>}
    {lesson?<section className="panel"><button className="button" onClick={()=>setLesson(null)}>返回课程</button><h2>{lesson.title}</h2><p>{lesson.access==='free'?'免费课程':'会员课程'} · {lesson.duration}</p><div className="member-lesson">{lesson.body}</div><button className="button" onClick={()=>onComplete?.(lesson.id)}>{completed.includes(lesson.id)?'已完成 · 点击撤销':'标记已完成'}</button><p className="fine-print">学习进度暂保存在当前浏览器。</p></section>:<div className="member-course-grid">{courses.map(c=><section className="panel" key={c.id}><span className="badge">{c.access==='free'?'免费课程':'高级会员解锁'}</span><h3>{c.title}</h3><p>{c.summary}</p><p className="fine-print">{c.duration}{completed.includes(c.id)?' · 已完成':''}</p><button className="button" disabled={busy} onClick={()=>open(c.id)}>{c.unlocked?'开始阅读':'查看解锁条件'}</button></section>)}</div>}
    {localCourses.some(c=>c.body)&&<section className="panel"><h3>本地研究文章</h3><p className="fine-print">保留此前在本浏览器编写的内容；这些文章没有公开发布，也不属于会员课程。</p>{localCourses.filter(c=>c.body).map(c=><details key={c.id}><summary>{c.title}</summary><div className="member-lesson">{c.body}</div></details>)}</section>}
  </div>;
}
