"""Course text is served only after server-side entitlement checks."""
import json
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from . import membership as m

router = APIRouter(prefix='/api/academy')


def courses():
    return json.loads(Path(__file__).with_name('academy-courses.json').read_text(encoding='utf-8'))


def allowed(course, user):
    return course['access'] == 'free' or bool(user and m.account(user)['allCourses'])


@router.get('/courses')
def listing(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    user = m.current_user(request)
    return {'courses': [{**{k: v for k, v in c.items() if k != 'body'}, 'unlocked': allowed(c, user)} for c in courses()]}


@router.get('/courses/{course_id}')
def read(course_id: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    course = next((c for c in courses() if c['id'] == course_id), None)
    if not course:
        raise HTTPException(404, '课程不存在。')
    if course['access'] != 'free':
        user = m.current_user(request)
        if not user:
            raise HTTPException(403, '此课程需要高级会员或专家会员，免费课程可直接阅读。')
        with m.database() as db:
            db.execute('BEGIN IMMEDIATE')
            info = m.entitlement(db, user['id'])
            if not m.PLANS[info['plan']]['all_courses']:
                raise HTTPException(403, '此课程需要高级会员或专家会员，免费课程可直接阅读。')
            db.execute('INSERT OR IGNORE INTO benefit_reads VALUES (?,?,?,?)',
                       (user['id'], info['period'], course_id, time.time()))
    return course
