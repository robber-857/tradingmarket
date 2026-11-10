"""One durable, evidence-bound daily edition. Never silently regenerate paid output."""
import asyncio
from datetime import timedelta
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dotenv import dotenv_values
from . import news, news_ai, narrative

DB = news.ROOT / 'server/cache/daily-briefs.sqlite3'
LOCK = asyncio.Lock()
VERSION = 'daily-editor-1.0'


def settings():
    values = dotenv_values(news.ROOT / '.env')
    hour = str(values.get('DAILY_BRIEF_HOUR', os.getenv('DAILY_BRIEF_HOUR', '8')))
    return {'enabled': values.get('DAILY_BRIEF_ENABLED', os.getenv('DAILY_BRIEF_ENABLED', '1')) != '0',
            'hour': int(hour) if hour.isdigit() and 0 <= int(hour) <= 23 else 8,
            'timezone': 'Australia/Sydney'}


@contextmanager
def connect():
    from .database import connect as connection
    with connection(DB, 'editions') as c:
        yield c


def listing(day=None):
    with connect() as c:
        if day:
            row = c.execute('SELECT * FROM editions WHERE day=?', (day,)).fetchone()
            if not row: raise news.NewsError(404, '该日尚未生成简报，离线期间不会补造历史判断')
            return {**dict(row), 'payload': json.loads(row['payload']) if row['payload'] else None}
        rows = [dict(r) for r in c.execute('SELECT day,status,attempts,updated,error FROM editions ORDER BY day DESC LIMIT 365')]
    cfg = settings()
    local = news.now().astimezone(news.SYDNEY)
    target = local.replace(hour=cfg['hour'], minute=0, second=0, microsecond=0)
    completed = any(r['day'] == local.date().isoformat() and r['status'] == 'ready' for r in rows)
    if completed: target += timedelta(days=1)
    return {'editions': rows, 'schedule': cfg, 'today': local.date().isoformat(),
            'nextRun': news.iso(target) if target > local else news.iso(local),
            'notice': '后端运行时按悉尼时间每日生成一次；当天错过时补跑一次，不回填过去日期。失败最多每天自动尝试三次，间隔至少一小时。'}


async def generate(manual=False):
    async with LOCK:
        day = news.now().astimezone(news.SYDNEY).date().isoformat()
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM editions WHERE day=?', (day,)).fetchone()
            if row and row['status'] == 'ready': return {**dict(row), 'payload': json.loads(row['payload'])}
            if row and row['status'] == 'generating':
                raise news.NewsError(409, '简报生成中；若服务曾中断，请使用重试中断任务，避免重复调用')
            if row and not manual and (row['attempts'] >= 3 or (news.now()-news.date_time(row['updated'])).total_seconds() < 3600):
                return None
            attempts = (row['attempts'] if row else 0) + 1
            c.execute('INSERT INTO editions VALUES (?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET status=excluded.status, attempts=excluded.attempts, updated=excluded.updated, payload=excluded.payload, error=excluded.error', (day, 'generating', attempts, news.iso(news.now()), None, None))
        try:
            snapshot = await news.feed()
            context, selected = news_ai.build_context(snapshot, None)
            # Stale evidence cannot silently become a newly generated daily briefing.
            selected = [i for i in selected if not i['stale']]
            if not selected: raise news.NewsError(503, '今日没有新鲜可用来源，暂不生成简报')
            context, selected = news_ai.build_context({**snapshot, 'articles': selected}, None)
            coverage = {k: sum(k in a['categories'] for a in selected) for k in ('stocks', 'crypto', 'macro')}
            context['coverage'] = coverage
            result = await narrative.call_openai(context, [], '生成今日市场简报：从材料中选择最值得关注的事件，简洁说明美股、加密货币和宏观的影响、风险与待验证条件。',
                instructions=news_ai.INSTRUCTIONS + '\n这是保存到历史的每日编辑简报。conclusion 概括核心矛盾；insights 最多三项，优先分别覆盖美股、加密货币、宏观，每项包括事件、传导和风险。来源缺少某领域就说明缺口，不能补造事件。watch_next 写下一步风险验证。不要把媒体指控变成已确认事实。',
                validator=news_ai.validate)
            payload = {**result, 'day': day, 'generatedAt': news.iso(news.now()), 'windowStart': snapshot['windowStart'],
                       'snapshotId': snapshot['snapshotId'], 'citations': context['registry'], 'articles': selected,
                       'coverage': coverage, 'promptVersion': VERSION,
                       'notice': 'AI 从最近二十四小时有限新闻摘要中选择重点；不是全网排行，不含实时价格归因。历史简报保留生成时判断。'}
            with connect() as c:
                c.execute('UPDATE editions SET status=?,updated=?,payload=?,error=NULL WHERE day=?', ('ready', news.iso(news.now()), json.dumps(payload, ensure_ascii=False), day))
            return listing(day)
        except (news.NewsError, narrative.AIError) as exc:
            with connect() as c: c.execute('UPDATE editions SET status=?,updated=?,error=? WHERE day=?', ('failed', news.iso(news.now()), exc.message, day))
            raise
        except Exception:
            with connect() as c: c.execute('UPDATE editions SET status=?,updated=?,error=? WHERE day=?', ('failed', news.iso(news.now()), '生成未完成，未保存部分结论', day))
            raise


async def retry_interrupted():
    if LOCK.locked(): raise news.NewsError(409, '当前任务仍在运行，请稍后检查')
    day = news.now().astimezone(news.SYDNEY).date().isoformat()
    with connect() as c:
        c.execute("UPDATE editions SET status='failed',error='用户重试中断任务' WHERE day=? AND status='generating'", (day,))
    return await generate(manual=True)


async def tick():
    cfg = settings()
    if cfg['enabled'] and news.now().astimezone(news.SYDNEY).hour >= cfg['hour']:
        await generate()


async def background():
    while True:
        try: await tick()
        except asyncio.CancelledError: raise
        except Exception: logging.getLogger(__name__).warning('Daily briefing incomplete; durable status retained')
        await asyncio.sleep(60)
