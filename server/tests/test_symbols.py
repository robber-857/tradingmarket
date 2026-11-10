import asyncio
import importlib
import json
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from server import sec
from server.app import app
from server.financials import build_report


DIRECTORY={'fields':['cik','name','ticker','exchange'],'data':[
    [2488,'Advanced Micro Devices','AMD','Nasdaq'],[1318605,'Tesla Inc','TSLA','Nasdaq'],
    [1067983,'Berkshire Hathaway','BRK-B','NYSE'],[5,'OTC Example','OTCX','OTC']]}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(sec,'_directory_memory',None)
    monkeypatch.setattr(sec,'_directory_lock',asyncio.Lock())
    monkeypatch.setattr(sec,'_lock',asyncio.Lock())


@pytest.mark.parametrize('input,expected',[(' tsla ','TSLA'),('$amd','AMD'),('brk.b','BRK-B'),('BRK-B','BRK-B')])
def test_ticker_normalization(input,expected):
    assert sec.normalize_symbol(input)==expected


@pytest.mark.parametrize('input',['../.env','https://example.com','A/B','A B','A%2FB','A'*30,'','123',None])
def test_ticker_rejects_paths_and_invalid_identifiers(input):
    with pytest.raises(sec.SymbolError):sec.normalize_symbol(input)


def fixture_directory():
    return {'records':sec.parse_directory(DIRECTORY),'source':{'stale':False,'url':sec.DIRECTORY_URL},'count':4}


def test_search_uses_official_name_and_exact_code_first(monkeypatch):
    async def directory():return fixture_directory()
    monkeypatch.setattr(sec,'company_directory',directory)
    assert asyncio.run(sec.search_companies('tesla'))['results'][0]['symbol']=='TSLA'
    assert asyncio.run(sec.search_companies('AMD'))['results'][0]['cik']=='0000002488'
    assert asyncio.run(sec.search_companies('brk.b'))['results'][0]['symbol']=='BRK-B'
    assert asyncio.run(sec.search_companies('nonexistent'))['results']==[]
    assert asyncio.run(sec.resolve_company('amd'))['symbol']=='AMD'
    for s,code in [('NOTREAL',404),('OTCX',422),('BTC',404)]:
        with pytest.raises(sec.SymbolError) as e:asyncio.run(sec.resolve_company(s))
        assert e.value.status==code


def test_directory_validation():
    bad={'fields':DIRECTORY['fields'],'data':[None,['bad','Bad','../X','NYSE']]}
    with pytest.raises(ValueError):sec.parse_directory(bad)


def test_stale_directory_is_marked_and_expired_directory_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(sec,'CACHE',tmp_path)
    monkeypatch.setenv('SEC_USER_AGENT','Test/1 test@example.org')
    path=tmp_path/'company-tickers-exchange.json';path.write_text(json.dumps(DIRECTORY))
    old=time.time()-2*86400;os.utime(path,(old,old))
    original=httpx.AsyncClient
    monkeypatch.setattr(sec.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(503)),**kw))
    assert asyncio.run(sec.company_directory())['source']['stale'] is True
    monkeypatch.setattr(sec,'_directory_memory',None)
    old=time.time()-8*86400;os.utime(path,(old,old))
    with pytest.raises(sec.DataUnavailable):asyncio.run(sec.company_directory())


def test_reassigned_ticker_cannot_reuse_another_cik_cache(tmp_path,monkeypatch):
    monkeypatch.setattr(sec,'CACHE',tmp_path)
    monkeypatch.setenv('SEC_USER_AGENT','Test/1 test@example.org')
    (tmp_path/'AMD-facts.json').write_text(json.dumps({'cik':999,'facts':{'fake':999}}))
    original=httpx.AsyncClient
    monkeypatch.setattr(sec.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(503)),**kw))
    with pytest.raises(sec.DataUnavailable):asyncio.run(sec.fetch_company('AMD',company={'symbol':'AMD','cik':'0000002488'}))


def test_dynamic_api_accepts_new_issuer_and_binds_cik(tmp_path,monkeypatch):
    module=importlib.import_module('server.app')
    monkeypatch.setattr(module,'REPORTS',tmp_path)
    async def resolve(s):return {**fixture_directory()['records']['AMD'],'directorySource':{'kind':'ticker_directory'}}
    async def fetch(s,refresh,company):
        assert s=='AMD' and company['cik']=='0000002488'
        return {'facts':{'us-gaap':{'Revenues':{}}}}, {'filings':{'recent':{'form':['10-Q']}},'tickers':['AMD'],'sic':'3674'}, []
    monkeypatch.setattr(module,'resolve_company',resolve);monkeypatch.setattr(module,'fetch_company',fetch)
    monkeypatch.setattr(module,'build_report',lambda s,c,*args:{'symbol':s,'company':c,'snapshotId':'c'*24})
    r=TestClient(app).get('/api/research/amd')
    assert r.status_code==200 and r.json()['symbol']=='AMD'
    assert (tmp_path/('c'*24+'.json')).exists()


def test_foreign_filing_is_not_interpreted_as_10q(monkeypatch):
    module=importlib.import_module('server.app')
    async def resolve(s):return {'symbol':'TSM','cik':'0001046179'}
    async def fetch(*args):return {'facts':{'ifrs-full':{}}}, {'filings':{'recent':{'form':['20-F','6-K']}}}, []
    monkeypatch.setattr(module,'resolve_company',resolve);monkeypatch.setattr(module,'fetch_company',fetch)
    r=TestClient(app).get('/api/research/TSM')
    assert r.status_code==422 and '20-F' in r.json()['detail']


@pytest.mark.parametrize('sic,tickers,dcf,multiples', [('3674',['AMD'],True,True),('6021',['BANK'],False,True),('7370',['GOOG','GOOGL'],False,False)])
def test_model_capabilities_follow_sector_and_security_basis(sic,tickers,dcf,multiples):
    record={'val':100,'start':'2025-01-01','end':'2025-03-31','filed':'2025-05-01','form':'10-Q','accn':'0000000001-25-000001'}
    facts={'cik':1,'facts':{'us-gaap':{'Revenues':{'units':{'USD':[record]}}}}}
    filings={'form':['10-Q'],'accessionNumber':[record['accn']],'primaryDocument':['test.htm'],'reportDate':[record['end']],'filingDate':[record['filed']]}
    r=build_report(tickers[0],{'sic':sic,'listedSecurities':tickers},facts,{'filings':{'recent':filings}},[])
    assert r['capabilities']['dcf']==dcf
    assert r['capabilities']['automaticMultiples']==multiples
