import asyncio
import pytest
from server import institution_translation as t, narrative


def test_translation_preserves_numbers_and_requires_chinese():
    assert t.validate('预计十月 CPI 上升 +0.3%。', 'We expect CPI to rise +0.3% in October.')
    assert t.validate('预计10月 CPI 上升 +0.3%。', 'We expect CPI to rise +0.3% in October.')
    with pytest.raises(ValueError):
        t.validate('预计9月 CPI 上升 +0.3%。', 'We expect CPI to rise +0.3% in October.')
    for text in ['预计上升0.4%。', '预计上升0.3%。', 'We expect +0.3%.', '预计+0.3%。http://fake.test']:
        with pytest.raises(ValueError):
            t.validate(text, 'We expect +0.3%.')


def test_snapshot_lookup_cache_dedup_and_changed_source(monkeypatch, tmp_path):
    monkeypatch.setattr(t, 'CACHE', tmp_path)
    monkeypatch.setattr(t, 'LOCK', asyncio.Lock())
    row={'id':'a'*24,'kind':'institution','institutionView':{'kind':'source_excerpt','excerpt':'We expect +0.3%.'}}
    monkeypatch.setattr(t.macro, 'load_snapshot', lambda _: {'publicForecasts':[row]})
    calls=[]
    async def generate(original):
        calls.append(original)
        return {'text':'预计 +0.3%。','kind':'ai_translation'}
    monkeypatch.setattr(t,'generate',generate)
    req=t.Request(snapshot_id='b'*24,record_id='a'*24)
    async def run():
        await asyncio.gather(t.translate(req),t.translate(req))
        row['institutionView']['excerpt']='We forecast +0.3%.'
        await t.translate(req)
    asyncio.run(run())
    assert len(calls)==2 and len(list(tmp_path.glob('*.json')))==2
    with pytest.raises(narrative.AIError):
        asyncio.run(t.translate(t.Request(snapshot_id='b'*24,record_id='c'*24)))


def test_failed_translation_is_not_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(t,'CACHE',tmp_path)
    monkeypatch.setattr(t,'LOCK',asyncio.Lock())
    monkeypatch.setattr(t.macro,'load_snapshot',lambda _: {'publicForecasts':[{'id':'a'*24,'kind':'institution','institutionView':{'kind':'source_excerpt','excerpt':'Test'}}]})
    async def fail(_): raise narrative.AIError(503,'Unavailable')
    monkeypatch.setattr(t,'generate',fail)
    with pytest.raises(narrative.AIError):
        asyncio.run(t.translate(t.Request(snapshot_id='b'*24,record_id='a'*24)))
    assert not list(tmp_path.iterdir())
