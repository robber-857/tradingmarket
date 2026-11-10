import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from server import dashboard_market as m


def chart(symbol='^NDX'):
    def ts(day):return datetime(2026,11,day,20,tzinfo=timezone.utc).timestamp()
    return {'chart':{'result':[{'meta':{'symbol':symbol,'regularMarketPrice':110,
        'regularMarketTime':ts(9),'exchangeTimezoneName':'America/New_York','chartPreviousClose':50},
        'timestamp':[ts(5),ts(6),ts(9)],'indicators':{'quote':[{'close':[95,100,109]}]}}]}}


def test_change_uses_prior_session_not_range_baseline():
    result=m.parse_chart(chart(),'^NDX')
    assert result['previousClose']==100
    assert result['change']==10
    assert result['changePct']==10


def test_null_history_does_not_invent_change():
    data=chart();data['chart']['result'][0]['indicators']['quote'][0]['close']=[None,None,109]
    result=m.parse_chart(data,'^NDX')
    assert result['price']==110 and result['changePct'] is None


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),True,-1])
def test_invalid_quote_rejected(value):
    data=chart();data['chart']['result'][0]['meta']['regularMarketPrice']=value
    with pytest.raises(ValueError):m.parse_chart(data,'^NDX')


def test_mismatched_instrument_rejected():
    with pytest.raises(ValueError):m.parse_chart(chart('^VIX'),'^NDX')


def test_provider_failure_marks_cache_and_preserves_quote_time(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'CACHE',tmp_path/'new-cache')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=chart()))) as client:
            first=await m.get_item(client,m.CATALOG[0])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as client:
            stale=await m.get_item(client,m.CATALOG[0])
            missing=await m.get_item(client,m.CATALOG[1])
        assert first['available'] and not first['stale']
        assert stale['stale'] and stale['asOf']==first['asOf']
        assert missing['price'] is None and not missing['available']
    asyncio.run(run())
