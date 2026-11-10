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


def test_watchlist_mapping_deduplication_and_cache(monkeypatch):
    monkeypatch.setattr(m, '_watch_cache', {})
    calls = []
    async def fake(client, spec):
        calls.append(spec[1])
        return {'symbol': spec[1], 'available': True, 'price': 110}
    monkeypatch.setattr(m, 'get_item', fake)
    async def run():
        result = await m.watchlist('nvda,BTC,ETH,SPX,NDX,BRK.B,NVDA')
        assert [i['watchSymbol'] for i in result['items']] == ['NVDA','BTC','ETH','SPX','NDX','BRK.B']
        assert calls == ['NVDA','BTC-USD','ETH-USD','^GSPC','^NDX','BRK-B']
        await m.watchlist('NVDA')
        assert len(calls) == 6
    asyncio.run(run())


@pytest.mark.parametrize('symbols', ['../../secret', 'A/B', ','.join('A'+str(i) for i in range(51))])
def test_watchlist_rejects_invalid_input(symbols):
    with pytest.raises(ValueError):asyncio.run(m.watchlist(symbols))


def test_watchlist_cache_expires_and_results_are_isolated(monkeypatch):
    monkeypatch.setattr(m, '_watch_cache', {})
    clock = [1000.0]
    monkeypatch.setattr(m.time, 'monotonic', lambda: clock[0])
    calls = []
    async def fake(client, spec):
        calls.append(spec[1])
        return {'symbol':spec[1], 'price':100 + len(calls), 'available':True}
    monkeypatch.setattr(m, 'get_item', fake)
    async def run():
        first = await m.watchlist('NVDA')
        first['items'][0]['price'] = -1
        cached = await m.watchlist('NVDA')
        assert cached['items'][0]['price'] == 101
        clock[0] += 301
        fresh = await m.watchlist('NVDA')
        assert fresh['items'][0]['price'] == 102
    asyncio.run(run())


def test_watchlist_partial_failure_and_stale_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'CACHE', tmp_path)
    monkeypatch.setattr(m, '_watch_cache', {})
    m.news.atomic_json(tmp_path / 'watch-MSFT.json', {
        'symbol':'MSFT', 'available':True, 'price':95, 'asOf':'2026-11-06T20:00:00+00:00',
        'history':[], 'changePct':None,
    })
    client_type = httpx.AsyncClient
    def respond(request):
        return httpx.Response(200, json=chart('NVDA')) if request.url.path.endswith('/NVDA') else httpx.Response(429)
    monkeypatch.setattr(m.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    result = asyncio.run(m.watchlist('NVDA,MSFT,UNKNOWN'))['items']
    assert result[0]['available'] and not result[0]['stale']
    assert result[1]['available'] and result[1]['stale']
    assert result[1]['asOf'] == '2026-11-06T20:00:00+00:00'
    assert not result[2]['available'] and result[2]['price'] is None


def test_watchlist_api_validation_and_empty_list():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    assert client.get('/api/market/watchlist').json() == {'items':[]}
    assert client.get('/api/market/watchlist', params={'symbols':'../../secret'}).status_code == 400
    assert client.get('/api/market/watchlist', params={'symbols':'A'*801}).status_code == 422


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
