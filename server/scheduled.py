"""Authenticated finite jobs: called by Supabase Cron, portable to EventBridge."""
import secrets
from fastapi import APIRouter, HTTPException, Request
from . import membership as m, news, daily_brief, public_forecasts
from .deployment import acquire, release

router = APIRouter(prefix='/api/cron')


@router.get('/{job}')
async def run_job(job: str, request: Request):
    expected = m.config('CRON_SECRET')
    if not expected or not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer '+expected):
        raise HTTPException(401, 'Unauthorized')
    if job not in ('news', 'brief', 'forecasts'):
        raise HTTPException(404, 'Unknown job')
    owner = acquire('cron:'+job)
    if not owner:
        return {'status': 'already_running'}
    try:
        if job == 'news':
            await news.feed()
        elif job == 'brief':
            await daily_brief.tick()
        else:
            await public_forecasts.update()
        return {'status': 'ok', 'job': job}
    finally:
        release('cron:'+job, owner)
