"""Deterministic, source-carrying financial normalization for US GAAP issuers.

Calendar dates, not fiscal-year labels or frame strings, identify a period.
Quarter cash flows are differenced from SAME fiscal-start YTD values. EPS and
weighted-average shares are never differenced. Missing facts remain missing.
"""
from datetime import date, timedelta
import hashlib
import json

VERSION = 'financials-1.1.0'
FORMS = {'10-Q', '10-K', '10-Q/A', '10-K/A'}
FLOW_TAGS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'],
    'gross_profit': ['GrossProfit'], 'operating_income': ['OperatingIncomeLoss'],
    'net_income': ['NetIncomeLoss', 'ProfitLoss'],
    'operating_cash_flow': ['NetCashProvidedByUsedInOperatingActivities'],
    'capex': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
    'stock_compensation': ['ShareBasedCompensation'],
    'interest': ['InterestExpenseNonoperating', 'InterestExpense', 'InterestAndDebtExpense'],
    'eps': ['EarningsPerShareDiluted'],
    'diluted_shares': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
}
STOCK_TAGS = {
    'assets': ['Assets'], 'liabilities': ['Liabilities'],
    'equity': ['StockholdersEquity'],
    'total_equity': ['StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', 'StockholdersEquity'],
    'cash': ['CashAndCashEquivalentsAtCarryingValue'],
    'current_assets': ['AssetsCurrent'], 'current_liabilities': ['LiabilitiesCurrent'],
    'debt_current': ['DebtCurrent'],
    'debt_lt_current': ['LongTermDebtCurrent'],
    'debt_lt_noncurrent': ['LongTermDebtNoncurrent'],
    'commercial_paper': ['CommercialPaper'], 'short_borrowings': ['ShortTermBorrowings'],
    'minority': ['MinorityInterest'], 'shares': ['CommonStockSharesOutstanding'],
}


def days(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def filing_url(cik, accn, document=None):
    root = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace("-", "")}'
    return f'{root}/{document}' if document else f'{root}/{accn}-index.htm'


class Extractor:
    def __init__(self, facts, submissions):
        self.facts = facts
        self.cik = str(facts['cik'])
        self.today = date.today().isoformat()
        recent = submissions['filings']['recent']
        self.filings = []
        self.docs = {}
        for i, form in enumerate(recent['form']):
            accn = recent['accessionNumber'][i]
            self.docs[accn] = recent['primaryDocument'][i]
            end = recent['reportDate'][i]
            if form in FORMS and end and end <= self.today and recent['filingDate'][i] <= self.today:
                self.filings.append({'form': form, 'end': end, 'filed': recent['filingDate'][i],
                                     'accn': accn, 'url': filing_url(self.cik, accn, self.docs[accn])})

    def records(self, tags, unit='USD', namespace='us-gaap'):
        for tag in tags:
            values = self.facts['facts'].get(namespace, {}).get(tag, {}).get('units', {}).get(unit, [])
            yield tag, [v for v in values if v.get('form') in FORMS and v.get('filed', '') <= self.today]

    def evidence(self, value, tag, unit='USD', namespace='us-gaap'):
        return {'value': value['val'], 'start': value.get('start'), 'end': value['end'],
                'filed': value['filed'], 'form': value['form'], 'accession': value['accn'],
                'tag': f'{namespace}:{tag}', 'unit': unit,
                'url': filing_url(self.cik, value['accn'], self.docs.get(value['accn']))}

    @staticmethod
    def latest(values):
        return max(values, key=lambda v: (v['filed'], v['accn'])) if values else None

    def direct(self, tags, end, duration=None, unit='USD'):
        for tag, vals in self.records(tags, unit):
            candidates = [v for v in vals if v['end'] == end and
                          (not v.get('start') if duration is None else v.get('start') and duration[0] <= days(v['start'], end) <= duration[1])]
            val = self.latest(candidates)
            if val:
                return fact(val['val'], [self.evidence(val, tag, unit)], 'disclosed')
        return missing('该日期没有匹配的标准 XBRL 标签')

    def quarter(self, key, end):
        tags = FLOW_TAGS[key]
        unit = 'USD/shares' if key == 'eps' else 'shares' if key == 'diluted_shares' else 'USD'
        direct = self.direct(tags, end, (70, 110), unit)
        if direct['value'] is not None or key in ('eps', 'diluted_shares'):
            return direct
        for tag, vals in self.records(tags, unit):
            current = [v for v in vals if v['end'] == end and v.get('start') and 150 <= days(v['start'], end) <= 380]
            cur = self.latest(current)
            if not cur:
                continue
            # Same tag, same fiscal start; no subtraction of a different fiscal year.
            previous = [v for v in vals if v.get('start') == cur['start'] and
                        v['end'] < end and 70 <= days(v['end'], end) - 1 <= 110 and v['filed'] <= cur['filed']]
            prev = self.latest(previous)
            if prev:
                start = (date.fromisoformat(prev['end']) + timedelta(days=1)).isoformat()
                return fact(cur['val'] - prev['val'], [self.evidence(cur, tag, unit), self.evidence(prev, tag, unit)],
                            'derived', '本财年累计值 − 上季度同财年累计值', start=start, end=end,
                            warning='差分跨申报版本；重述需复核' if cur['accn'] != prev['accn'] else None)
        return missing('无独立季度披露，且不能安全地由同财年累计值还原')

    def shares(self, end, cutoff):
        direct = self.direct(STOCK_TAGS['shares'], end, unit='shares')
        if direct['value'] is not None:
            return direct
        for tag, vals in self.records(['EntityCommonStockSharesOutstanding'], 'shares', 'dei'):
            valid = [v for v in vals if end <= v['end'] <= cutoff and not v.get('start')]
            latest = self.latest(valid)
            if latest:
                return fact(latest['val'], [self.evidence(latest, tag, 'shares', 'dei')], 'disclosed',
                            warning='股数日期为申报前披露日，可能不同于财报期末')
        return missing('缺少可对应的期末或申报前流通股数；不使用加权平均股数冒充')


def fact(value, evidence=None, status='calculated', formula=None, **kwargs):
    return {'value': value, 'status': status, 'evidence': evidence or [], 'formula': formula, **kwargs}


def missing(reason):
    return fact(None, status='missing', reason=reason)


def calc(inputs, fn, formula):
    if any(x['value'] is None for x in inputs):
        return missing('所需输入缺失，不补零、不估算')
    evidence = []
    for x in inputs:
        for e in x['evidence']:
            if e not in evidence:
                evidence.append(e)
    return fact(fn(*[x['value'] for x in inputs]), evidence, formula=formula)


def ratio(a, b, formula, positive=True):
    if b['value'] is not None and (b['value'] <= 0 if positive else b['value'] == 0):
        return missing('分母非正，比例不具备可比较含义' if positive else '分母为零')
    return calc([a, b], lambda x, y: x / y, formula)


def growth(a, b):
    if b['value'] is not None and b['value'] <= 0:
        return missing('比较基期为零或亏损，使用绝对变化而非误导性的增长率')
    return calc([a, b], lambda x, y: x / y - 1, '本期 / 正值基期 − 1')


def debt_from(stock):
    # DebtCurrent already includes current maturities; never add them twice.
    if stock['debt_current']['value'] is not None:
        inputs = [stock['debt_current'], stock['debt_lt_noncurrent']]
    else:
        inputs = [stock['debt_lt_current'], stock['debt_lt_noncurrent']]
        inputs += [stock[k] for k in ('commercial_paper', 'short_borrowings') if stock[k]['value'] is not None]
    return calc(inputs, lambda *xs: sum(xs), '已披露当期债务 + 非流动长期债务（不重复计算到期部分）')


def build_report(symbol, company, facts, submissions, sources):
    x = Extractor(facts, submissions)
    ends = sorted({f['end'] for f in x.filings}, reverse=True)[:16]
    if not ends:
        raise ValueError('未找到正式 10-Q / 10-K 报告')
    quarters = []
    for end in reversed(ends):
        filing = max((f for f in x.filings if f['end'] == end), key=lambda f: (f['filed'], f['accn']))
        flow = {k: x.quarter(k, end) for k in FLOW_TAGS}
        revenue = flow['revenue']
        if revenue['value'] is None:
            continue
        start = revenue.get('start') or revenue['evidence'][0].get('start')
        stock = {k: x.direct(tags, end, unit='shares' if k == 'shares' else 'USD') for k, tags in STOCK_TAGS.items()}
        stock['debt'] = debt_from(stock)
        stock['shares'] = x.shares(end, filing['filed'])
        if stock['liabilities']['value'] is None:
            stock['liabilities'] = calc([stock['assets'], stock['total_equity']], lambda a, e: a-e, '总资产 − 含少数股东权益的总权益')
        flow['free_cash_flow'] = calc([flow['operating_cash_flow'], flow['capex']], lambda a, b: a-b, '经营现金流 − 资本性现金支出；不等于 FCFF')
        metrics = {
            'gross_margin': ratio(flow['gross_profit'], revenue, '毛利润 / 营收'),
            'operating_margin': ratio(flow['operating_income'], revenue, '营业利润 / 营收'),
            'net_margin': ratio(flow['net_income'], revenue, '净利润 / 营收'),
            'capex_intensity': ratio(flow['capex'], revenue, '资本性现金支出 / 营收'),
            'cash_conversion': ratio(flow['operating_cash_flow'], flow['net_income'], '经营现金流 / 正值净利润'),
            'liability_ratio': ratio(stock['liabilities'], stock['assets'], '总负债 / 总资产；不等于有息债务率'),
            'current_ratio': ratio(stock['current_assets'], stock['current_liabilities'], '流动资产 / 流动负债'),
            'net_debt': calc([stock['debt'], stock['cash']], lambda d,c:d-c, '已映射有息债务 − 现金及现金等价物'),
        }
        quarters.append({'end': end, 'start': start, 'filing': filing, 'flow': flow, 'stock': stock, 'metrics': metrics})
    for i, q in enumerate(quarters):
        prior = quarters[i-1] if i and 70 <= days(quarters[i-1]['end'], q['end'])-1 <= 110 else None
        yoy = next((r for r in quarters[:i] if 350 <= days(r['end'], q['end'])-1 <= 380), None)
        q['metrics']['revenue_qoq'] = growth(q['flow']['revenue'], prior['flow']['revenue']) if prior else missing('缺少相邻季度')
        q['metrics']['revenue_yoy'] = growth(q['flow']['revenue'], yoy['flow']['revenue']) if yoy else missing('缺少上年同季')
        q['metrics']['profit_yoy'] = growth(q['flow']['net_income'], yoy['flow']['net_income']) if yoy else missing('缺少上年同季')
        q['metrics']['profit_qoq'] = growth(q['flow']['net_income'], prior['flow']['net_income']) if prior else missing('缺少相邻季度')
        q['metrics']['gross_margin_yoy'] = calc([q['metrics']['gross_margin'], yoy['metrics']['gross_margin']], lambda a,b:a-b, '本季毛利率 − 上年同季毛利率（百分点）') if yoy else missing('缺少上年同季')
        q['metrics']['share_dilution_yoy'] = growth(q['flow']['diluted_shares'], yoy['flow']['diluted_shares']) if yoy else missing('缺少上年同季可比稀释股数')
        window = quarters[max(0,i-3):i+1]
        contiguous = len(window) == 4 and all(b['start'] and days(a['end'],b['start'])-1 == 1 for a,b in zip(window, window[1:]))
        q['ttm'] = {k: calc([r['flow'][k] for r in window], lambda *xs:sum(xs), '连续四个独立季度之和') if contiguous else missing('不足四个连续季度，不能计算 TTM') for k in FLOW_TAGS if k not in ('eps','diluted_shares')}
        q['ttm']['free_cash_flow'] = calc([q['ttm']['operating_cash_flow'], q['ttm']['capex']], lambda a,b:a-b, 'TTM 经营现金流 − TTM 资本性现金支出')
        q['ttm']['operating_margin'] = ratio(q['ttm']['operating_income'], q['ttm']['revenue'], 'TTM 营业利润 / TTM 营收')
        q['ttm']['cash_conversion'] = ratio(q['ttm']['operating_cash_flow'], q['ttm']['net_income'], 'TTM 经营现金流 / 正值 TTM 净利润')
        q['ttm']['interest_coverage'] = ratio(q['ttm']['operating_income'], q['ttm']['interest'], 'TTM 营业利润 / 正值 TTM 利息费用')
        q['investedCapital'] = calc([q['stock']['debt'],q['stock']['total_equity'],q['stock']['cash']],lambda d,e,c:d+e-c,'已映射账面债务 + 含少数股东的权益 − 现金')
        q['averageInvestedCapital'] = calc([q['investedCapital'], yoy['investedCapital']],lambda a,b:(a+b)/2,'本期与上年同期期末投入资本的平均值') if yoy else missing('缺少上年同期投入资本')
        q['insights'] = insights(q)
    if not quarters:
        raise ValueError('没有可还原的独立季度')
    sic = int(company.get('sic') or 0)
    multiple = len(company.get('listedSecurities', [])) > 1
    sector_model = 6000 <= sic < 7000
    reason = ('银行、保险、REIT 等金融类发行人需要专用资本与估值模型，暂停通用 FCFF/DCF。' if sector_model else
              '该发行人有多个上市证券；所选证券与公司总股权的换算口径未核验，暂停每股 DCF 与自动倍数。' if multiple else None)
    normalized = {'symbol': symbol, 'company': company, 'engineVersion': VERSION,
                  'quarters': list(reversed(quarters[-8:])), 'sources': sources,
                  'basis': 'latest_restated', 'latestReportEnd': quarters[-1]['end'],
                  'latestFiledReportEnd': ends[0],
                  'capabilities': {'dcf':not bool(reason),'dcfReason':reason,'automaticMultiples':not multiple,
                                   'multiplesReason':'多个上市证券的股数与所选证券口径未核验，暂停自动市值倍数。' if multiple else None},
                  'limitations': ['按最新可得修订值重建，非当时可知数据，不能直接用于回测。',
                      '仅映射标准合并 XBRL 标签；分部、自定义标签与特殊会计调整需要复核。',
                      '现金流差分可能跨申报版本；股数与利润率受拆股、减值和一次性事项影响。',
                      '有息债务为已映射账面口径，租赁、可转债、少数股东和其他权益索偿需复核。'],
                  'unavailable': ['实时股价与成交量', '市场一致预期', '管理层指引全文解析', '股价异动因果归因']}
    normalized['snapshotId'] = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:24]
    return normalized


def insights(q):
    f,m,t = q['flow'],q['metrics'],q['ttm']
    yoy=m['revenue_yoy']['value']; gm=m['gross_margin_yoy']['value']
    first = f'营收同比 {yoy:+.1%}' if yoy is not None else '收入比较基期不足'
    if gm is not None:
        first += f'，毛利率变动 {gm*100:+.1f} 个百分点。'
    cash=t['free_cash_flow']['value']; net=t['net_income']['value']; conv=t['cash_conversion']['value']
    second = '现金流口径不完整，暂不判断盈利含金量。'
    if cash is not None:
        second = f'近四季现金流减资本支出为 {cash/1e9:.2f} 十亿美元。'
        if cash<0:
            second += '经营现金尚未覆盖资本性现金支出。'
        elif conv is not None:
            second += f'每 $1 净利润对应 ${conv:.2f} 经营现金流。'
        elif net is not None and net <= 0:
            second += '近四季净利润非正，现金利润比不适用。'
    liabilities=m['liability_ratio']['value']; capex=m['capex_intensity']['value']
    third = f'本季资本性现金支出占营收 {capex:.1%}。' if capex is not None else '资本开支数据缺失。'
    if liabilities is not None:
        third+=f' 总负债率 {liabilities:.1%}，需与债务期限一起读。'
    dilution=m['share_dilution_yoy']['value']
    if dilution is not None and dilution > .03:
        third=f'稀释口径股数同比增加 {dilution:.1%}。需核对融资与拆股，判断每股收益是否被摊薄。'
    return [{'title':'增长是否改善？','text':first,'kind':'计算事实','metrics':['revenue_yoy','gross_margin_yoy']},
            {'title':'利润能否变成现金？','text':second,'kind':'规则解读','metrics':['free_cash_flow','cash_conversion']},
            {'title':'增长付出了什么代价？','text':third,'kind':'规则解读','metrics':['share_dilution_yoy'] if dilution is not None and dilution > .03 else ['capex_intensity','liability_ratio']}]
