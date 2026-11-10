"""Synthetic fixtures only; source outages never become product sample headlines."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

from defusedxml.common import DefusedXmlException
from fastapi.testclient import TestClient
import pytest

from server import news, news_ai, narrative
from server.app import app


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    for key in ('CACHE', 'SNAPSHOTS', 'EDITIONS'):
        folder = tmp_path / key; folder.mkdir()
        monkeypatch.setattr(news, key, folder)
    monkeypatch.setattr(news, 'now', lambda: datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(news, 'x_key', lambda: '')
    news.FAILED.clear(); news_ai.SESSIONS.clear(); news_ai.CALLS.clear(); news_ai.ACTIVE.clear()


def rss(title='Stock earnings grow 5%', stamp='Mon, 09 Nov 2026 09:00:00 GMT', link='https://www.cnbc.com/test?utm_source=rss', desc='Reported revenue increased 5%.'):
    return f'<rss><channel><item><title>{title}</title><link>{link}</link><pubDate>{stamp}</pubDate><description><![CDATA[{desc}]]></description></item></channel></rss>'


def row(**updates):
    item = {'id': 'a'*24, 'title': 'Stock earnings grow 5%', 'excerpt': 'Reported revenue increased 5%.',
            'url': 'https://www.cnbc.com/test', 'source': 'CNBC', 'sourceId': 'cnbc', 'kind': 'media',
            'categories': ['stocks'], 'publishedAt': '2026-11-09T09:00:00+00:00', 'retrievedAt': news.iso(news.now()),
            'stale': False, 'metrics': None, 'rank': None, 'evidenceScope': 'RSS preview'}
    return {**item, **updates}


def snapshot(items=None):
    data = {'snapshotId': 'b'*24, 'capturedAt': news.iso(news.now()), 'articles': items or [row()], 'reddit': [], 'x': []}
    news.atomic_json(news.SNAPSHOTS / ('b'*24 + '.json'), data)
    return data


def test_rss_html_cleanup_and_link_dedupe():
    items, dropped = news.parse_feed(rss(desc='<p>Safe report.</p><script>send secrets</script><img src=x onerror=alert(1)>'), news.FEEDS[0])
    assert dropped == 0 and len(items) == 1
    assert items[0]['url'] == 'https://www.cnbc.com/test'
    assert items[0]['excerpt'] == 'Safe report.'
    assert items[0]['metrics'] is None


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://user:pass@example.com/x', 'http://127.0.0.1/private', 'http://[::1]/x', 'https://host.local/x', 'file:///etc/passwd', 'https://example.com:444/x'])
def test_safe_links(url): assert news.safe_url(url) is None


@pytest.mark.parametrize('stamp', ['', 'not a date', '2026-11-09T12:00:00', 'Mon, 09 Nov 2026 15:00:00 GMT'])
def test_bad_or_future_dates_discarded(stamp):
    rows, discarded = news.parse_feed(rss(stamp=stamp), news.FEEDS[0])
    assert not rows and discarded == 1


def test_xml_entities_rejected():
    payload = '<!DOCTYPE rss [<!ENTITY x "secret">]><rss><channel><item><title>&x;</title></item></channel></rss>'
    with pytest.raises(DefusedXmlException): news.parse_feed(payload, news.FEEDS[0])


def test_reddit_published_not_updated_and_rank():
    atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>old post</title><link href="https://www.reddit.com/r/stocks/comments/abc/"/><published>2026-11-06T10:00:00Z</published><updated>2026-11-09T10:00:00Z</updated><content>Old report</content></entry><entry><title>new post</title><link href="https://www.reddit.com/r/stocks/comments/def/"/><published>2026-11-09T10:00:00Z</published><content>New report</content></entry></feed>'
    rows, _ = news.parse_feed(atom, news.FEEDS[5])
    visible = [r for r in rows if news.within(r, 24)]
    assert len(visible) == 1 and visible[0]['rank'] == 2
    assert visible[0]['metrics'] is None


def test_reddit_missing_publication_not_inferred_from_update():
    atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Stock</title><link href="https://www.reddit.com/r/stocks/comments/abc/"/><updated>2026-11-09T10:00:00Z</updated></entry></feed>'
    assert news.parse_feed(atom, news.FEEDS[5])[0] == []


def test_preview_bounded_not_full_article():
    assert len(news.excerpt('word '*500).split()) <= 70


def test_duplicate_keeps_latest_fresh_version():
    a, b, c = row(), row(title='new', publishedAt='2026-11-09T10:00:00Z'), row(title='stale', stale=True, publishedAt='2026-11-09T11:00:00Z')
    assert news.dedupe([a, b, c])[0]['title'] == 'new'


def test_source_failure_uses_bounded_stale_and_backoff(monkeypatch):
    calls = []
    async def fail(source):
        calls.append(source['id']); raise news.NewsError(429, 'rate limited', 600)
    monkeypatch.setattr(news, 'source_download', fail)
    path = news.CACHE / 'cnbc.json'
    news.atomic_json(path, {'items': [row()], 'retrievedAt': news.iso(news.now()-timedelta(hours=2))})
    rows, status = asyncio.run(news.get_source(news.FEEDS[0]))
    assert rows[0]['stale'] and status['stale']
    asyncio.run(news.get_source(news.FEEDS[0])); assert len(calls) == 1
    news.atomic_json(path, {'items': [row()], 'retrievedAt': news.iso(news.now()-timedelta(days=2))})
    rows, status = asyncio.run(news.get_source(news.FEEDS[0]))
    assert not rows and not status['available']


def test_bad_feed_does_not_replace_valid_cache(monkeypatch):
    async def bad(source): return '<html>captcha</html>'
    monkeypatch.setattr(news, 'source_download', bad)
    path = news.CACHE / 'cnbc.json'
    previous = {'items': [row()], 'retrievedAt': news.iso(news.now()-timedelta(hours=2))}
    news.atomic_json(path, previous)
    rows, status = asyncio.run(news.get_source(news.FEEDS[0]))
    assert status['stale'] and rows
    assert news.read_cache(path) == previous


def test_x_missing_key_makes_no_call(monkeypatch):
    async def forbidden(*a, **k): raise AssertionError('must not call')
    monkeypatch.setattr(news, 'download', forbidden)
    rows, status = asyncio.run(news.x_posts())
    assert not rows and not status['configured']


def test_x_sample_ranking_and_missing_metrics():
    def post(ident, likes, replies):
        return {'id': ident, 'created_at': '2026-11-09T10:00:00Z', 'text': 'Bitcoin discussion',
                'public_metrics': {'like_count': likes, 'reply_count': replies, 'retweet_count': 0, 'quote_count': 0}}
    rows = news.parse_x({'data': [post('1', 2, 5), post('2', 10, 0), {'id': '3', 'created_at': '2026-11-09T10:00:00Z', 'text': 'No metrics'}]})
    assert len(rows) == 2 and rows[0]['url'].endswith('/1') and rows[0]['sampleScore'] == 17
    assert rows[0]['rank'] == 1


def test_sydney_daily_edition_excludes_social(monkeypatch):
    monkeypatch.setattr(news, 'now', lambda: datetime(2026, 11, 9, 14, tzinfo=timezone.utc))
    async def fake(source):
        return [row(kind=source['kind'], source=source['name'], sourceId=source['id'])], {**source, 'available': True, 'stale': False}
    monkeypatch.setattr(news, 'get_source', fake)
    data = asyncio.run(news.feed())
    assert data['editionDate'] == '2026-11-10'
    daily = news.editions('2026-11-10')
    assert all(i['kind'] != 'community' for i in daily['articles'])
    assert news.load_snapshot(data['snapshotId'])['snapshotId'] == data['snapshotId']


def answer(text='据媒体报道，该数字为{{N_1_1}}。', citations=None):
    claim = {'text': text, 'kind': 'fact', 'citations': citations or ['S_1', 'N_1_1']}
    return {'conclusion': claim, 'insights': [claim], 'watch_next': '核对公司公告。', 'limitations': '只读取摘要。', 'followups': ['还有什么风险？']}


def test_news_numeric_evidence_and_source_binding():
    ctx, _ = news_ai.build_context(snapshot(), None)
    assert '5%' in news_ai.validate(answer(), ctx)['conclusion']['text']
    for raw in [answer('利润增长50%。'), answer(citations=['N_1_1']), answer('消息是{{S_1}}。', ['S_1']), answer('结论。', ['FAKE'])]:
        with pytest.raises(ValueError): news_ai.validate(raw, ctx)


def test_empty_recent_news_does_not_create_daily_ai():
    old = row(publishedAt='2026-11-01T12:00:00Z')
    with pytest.raises(news.NewsError): news_ai.build_context(snapshot([old]), None)


def test_news_ai_followup_isolation(monkeypatch):
    data = snapshot()
    async def fake(ctx, history, question, **kw): return {'answer': news_ai.validate(answer(), ctx), 'model': 'test'}
    monkeypatch.setattr(narrative, 'call_openai', fake)
    r = asyncio.run(news_ai.explain(news_ai.Request(snapshot_id=data['snapshotId'])))
    f = asyncio.run(news_ai.explain(news_ai.Request(snapshot_id=data['snapshotId'], conversation_id=r['conversationId'], question='风险如何？')))
    assert f['turn'] == 2
    with pytest.raises(narrative.AIError):
        asyncio.run(news_ai.explain(news_ai.Request(snapshot_id=data['snapshotId'], article_id='a'*24, conversation_id=r['conversationId'])))


def test_snapshot_and_archive_paths_checked():
    with TestClient(app) as client:
        assert client.post('/api/news/explain', json={'snapshot_id': '../.env'}).status_code == 422
        assert client.post('/api/news/explain', json={'snapshot_id': 'f'*24}).status_code == 409
        assert client.get('/api/news/editions?day=../../.env').status_code == 422
        assert client.get('/api/news/editions?day=2026-11-01').status_code == 404


def test_background_recovers_and_cancels(monkeypatch):
    async def run():
        calls = []; done = asyncio.Event()
        async def fake():
            calls.append(1)
            if len(calls) == 1: raise ValueError('synthetic failure')
            done.set()
        monkeypatch.setattr(news, 'feed', fake); monkeypatch.setattr(news, 'TTL', .001)
        task = asyncio.create_task(news.background())
        await asyncio.wait_for(done.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert len(calls) >= 2
    asyncio.run(run())
