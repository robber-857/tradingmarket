import json
import asyncio
from contextlib import asynccontextmanager, suppress
import os
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .financials import VERSION, build_report
from .sec import COMPANIES, ROOT, DataUnavailable, SymbolError, fetch_company, resolve_company, search_companies, normalize_symbol
from .valuation import Assumptions, WaccInputs, BetaInputs, calculate_beta, calculate_wacc, valuation_bundle
from . import narrative, market, macro, macro_ai, news, news_ai, daily_brief, options, options_ai, option_strategies, live_strategies, public_forecasts
from . import dashboard_market


@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(news.background()) if os.getenv('NEWS_BACKGROUND_ENABLED', '1') != '0' else None
    daily_worker = asyncio.create_task(daily_brief.background()) if os.getenv('NEWS_BACKGROUND_ENABLED', '1') != '0' else None
    forecast_worker = asyncio.create_task(public_forecasts.background()) if os.getenv('PUBLIC_FORECAST_BACKGROUND_ENABLED', '1') != '0' else None
    try:
        yield
    finally:
        for task in (worker, daily_worker, forecast_worker):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError): await task


app=FastAPI(title='Meridian research engine', version='0.3.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:4173'],
                   allow_methods=['GET','POST'],allow_headers=['Content-Type'])
REPORTS=ROOT/'server'/'reports'
REPORTS.mkdir(exist_ok=True)


@app.get('/api/market/overview')
async def market_overview():
    return await dashboard_market.overview()


@app.get('/api/briefs')
def briefs(day:date | None=None):
    try: return daily_brief.listing(day.isoformat() if day else None)
    except news.NewsError as exc: raise HTTPException(exc.status, exc.message) from exc


@app.post('/api/briefs/generate')
async def generate_brief(retry_interrupted:bool=False):
    try: return await daily_brief.retry_interrupted() if retry_interrupted else await daily_brief.generate(manual=True)
    except (news.NewsError,narrative.AIError) as exc: raise HTTPException(exc.status,exc.message) from exc


@app.get('/api/options/earnings')
async def options_earnings(day:date | None=None):
    try: return await options.earnings(day or news.now().astimezone(options.ET).date())
    except news.NewsError as exc: raise HTTPException(exc.status,exc.message) from exc


@app.post('/api/options/analyze')
async def analyze_options(request:options.AnalysisRequest):
    try: return await options.research(request)
    except (news.NewsError,SymbolError) as exc: raise HTTPException(exc.status,exc.message) from exc


@app.post('/api/options/strategy')
def strategy_options(request:option_strategies.StrategyRequest):
    return option_strategies.calculate(request)


@app.post('/api/options/explain')
async def explain_options(request:options_ai.Request):
    try: return await options_ai.explain(request)
    except (news.NewsError,narrative.AIError) as exc: raise HTTPException(exc.status,exc.message) from exc


@app.get('/api/options/live-templates')
def live_templates(snapshot_id:str):
    try:return live_strategies.templates(snapshot_id)
    except news.NewsError as exc:raise HTTPException(exc.status,exc.message) from exc


@app.post('/api/options/compare')
def live_compare(request:live_strategies.CompareRequest):
    try:return live_strategies.compare(request)
    except news.NewsError as exc:raise HTTPException(exc.status,exc.message) from exc


@app.get('/api/news/feed')
async def news_feed():
    return await news.feed()


@app.get('/api/news/editions')
def news_editions(day:str | None=Query(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')):
    try: return news.editions(day)
    except news.NewsError as exc: raise HTTPException(exc.status, exc.message) from exc


@app.post('/api/news/explain')
async def news_explain(request:news_ai.Request):
    try: return await news_ai.explain(request)
    except (news.NewsError, narrative.AIError) as exc: raise HTTPException(exc.status, exc.message) from exc


@app.get('/api/macro/calendar')
async def macro_calendar(start:date | None=None, end:date | None=None):
    try:
        return await macro.calendar(start, end)
    except macro.MacroError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@app.post('/api/macro/explain')
async def macro_explain(request:macro_ai.Request):
    try:
        return await macro_ai.explain(request)
    except (macro.MacroError, narrative.AIError) as exc:
        raise HTTPException(exc.status, exc.message) from exc


@app.get('/api/health')
def health():
    return {'status':'ok','engineVersion':VERSION,'llmEnabled':narrative.status()['configured'],'symbolDiscovery':'SEC directory','featured':list(COMPANIES)}


@app.get('/api/research/assets')
async def supported_assets(q:str=Query(default='',max_length=80)):
    try: return await search_companies(q)
    except DataUnavailable as exc: raise HTTPException(503,str(exc)) from exc


@app.get('/api/research/{symbol}')
async def research(symbol:str,refresh:bool=False):
    try:
        company=await resolve_company(symbol)
        symbol=company['symbol']
        facts,submissions,sources=await fetch_company(symbol,refresh,company)
        forms=set(submissions.get('filings',{}).get('recent',{}).get('form',[]))
        if not forms.intersection({'10-Q','10-K','10-Q/A','10-K/A'}):
            raise SymbolError(422,'该发行人没有当前模型所需的 10-Q / 10-K。20-F、6-K、基金及其他申报需独立模型，当前不自动套用季度财报分析。')
        if not facts.get('facts',{}).get('us-gaap'):
            raise SymbolError(422,'该发行人缺少 US GAAP 标准财务标签；IFRS 与其他口径尚未映射，不自动转换。')
        tickers=submissions.get('tickers',[])
        if tickers and symbol not in [normalize_symbol(t) for t in tickers]:
            raise SymbolError(409,'SEC 目录与发行人现有代码不一致，可能发生更名或代码变更，请稍后刷新。')
        company.update({'english':submissions.get('name') or company['english'], 'sic':submissions.get('sic'),
                        'industry':submissions.get('sicDescription'), 'listedSecurities':tickers})
        try:
            report=build_report(symbol,company,facts,submissions,sources+[company['directorySource']])
        except ValueError as exc:
            if 6000 <= int(company.get('sic') or 0) < 7000:
                raise SymbolError(422,'该金融类发行人的收入与资本标签需要专用模型，目前不能可靠生成通用季度分析。可查看 SEC 原始申报；不会补造缺失指标。') from exc
            raise SymbolError(422,'已找到发行人，但无法从标准 USD/US GAAP 标签还原完整季度。自定义标签、非美元或特殊财年需额外映射，当前不补造数据。') from exc
        path=REPORTS/f'{report["snapshotId"]}.json'
        if not path.exists():
            path.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        return report
    except SymbolError as exc:
        raise HTTPException(exc.status,exc.message) from exc
    except DataUnavailable as exc:
        raise HTTPException(503,str(exc)) from exc
    except (ValueError,KeyError) as exc:
        raise HTTPException(422,'官方数据结构无法完整解析，暂停分析；请检查数据口径。') from exc


class ValuationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_id:str=Field(pattern=r'^[0-9a-f]{24}$')
    report_end:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    assumptions:Assumptions
    market_snapshot_id:str | None=Field(default=None,pattern=r'^[0-9a-f]{24}$')


@app.post('/api/research/{symbol}/valuation')
def valuation(symbol:str,request:ValuationRequest):
    path=REPORTS/f'{request.snapshot_id}.json'
    if not path.exists():
        raise HTTPException(409,'研究快照不存在，请重新加载财报后计算。')
    report=json.loads(path.read_text(encoding='utf-8'))
    if report['symbol']!=symbol.upper():
        raise HTTPException(409,'快照与股票代码不匹配。')
    quarter=next((q for q in report['quarters'] if q['end']==request.report_end),None)
    if not quarter:
        raise HTTPException(422,'所选报告期不在快照中。')
    try:
        if report.get('capabilities',{}).get('dcf') is False:
            raise HTTPException(422,report['capabilities']['dcfReason'])
        snapshot=market.load_snapshot(request.market_snapshot_id,report,quarter) if request.market_snapshot_id else None
        assumptions=market.bind_assumptions(request.assumptions,snapshot) if snapshot else request.assumptions
        result=valuation_bundle(quarter,assumptions)
        if snapshot:
            result['multiples']=snapshot['multiples']
            result['marketSnapshotId']=snapshot['marketSnapshotId']
        return {**result,'snapshotId':request.snapshot_id,'symbol':report['symbol'],
                'calculatedAt':datetime.now(timezone.utc).isoformat()}
    except market.MarketError as exc:
        raise HTTPException(exc.status,exc.message) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@app.post('/api/research-tools/wacc')
def wacc(request:WaccInputs):
    return calculate_wacc(request)


@app.post('/api/research-tools/beta')
def beta(request:BetaInputs):
    try: return calculate_beta(request)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@app.get('/api/ai/status')
def ai_status():
    return narrative.status()


@app.get('/api/market/status')
def market_status():
    return market.status()


@app.get('/api/research/{symbol}/market')
async def market_data(symbol:str,snapshot_id:str):
    import re
    if not re.fullmatch(r'[0-9a-f]{24}',snapshot_id): raise HTTPException(422,'财报快照格式无效。')
    path=REPORTS/f'{snapshot_id}.json'
    if not path.exists(): raise HTTPException(409,'请先加载正式财报。')
    report=json.loads(path.read_text(encoding='utf-8'))
    if report['symbol']!=symbol.upper(): raise HTTPException(409,'财报快照与股票不匹配。')
    try: return await market.build_market(report)
    except market.MarketError as exc: raise HTTPException(exc.status,exc.message) from exc


@app.post('/api/research/{symbol}/explain')
async def explain(symbol:str,request:narrative.NarrativeRequest):
    path=REPORTS/f'{request.snapshot_id}.json'
    if not path.exists(): raise HTTPException(409,'快照不存在，请刷新财报后重试。')
    report=json.loads(path.read_text(encoding='utf-8'))
    if report['symbol']!=symbol.upper(): raise HTTPException(409,'快照与股票代码不匹配。')
    quarter=next((q for q in report['quarters'] if q['end']==request.report_end),None)
    if not quarter: raise HTTPException(422,'报告期不在当前快照中。')
    try: return await narrative.explain(report,quarter,request)
    except narrative.AIError as exc: raise HTTPException(exc.status,exc.message) from exc
