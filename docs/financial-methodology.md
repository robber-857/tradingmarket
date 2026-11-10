# 财报与估值方法 v1.0

本文件描述已实现的确定性计算，不表示模型能预测股价。会计指标、公司金融估值框架与研究者的预测假设必须分开。没有一套受权威经济学家认可的万能公式能自动判定所有公司的投资价值。

## 依据与数据

- [SEC 官方 Company Facts / Submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)：合并口径标准 XBRL 标签与正式申报目录。
- [SEC 请求规则](https://www.sec.gov/about/developer-resources)：后端声明应用与联系邮箱，串行、缓存与节流请求。当前没有使用需要付费密钥的财报供应商。
- [CFA Institute：Free Cash Flow Valuation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation)：FCFF、FCFE 与折现率匹配，以及企业价值到股权价值的转换。
- [Damodaran：Valuation](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html)：现金流、增长和风险的估值框架。
- [Damodaran：Growth and Value Drivers](https://people.stern.nyu.edu/adamodar/New_Home_Page/littlebook/growthvaluedrivers.htm)：用销售资本比连接增长与再投资。
- [Damodaran：Terminal Value and Excess Returns](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm)：稳定期增长、资本回报与再投资的一致性。
- [Damodaran：Return Measures](https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf)：资本回报率的定义与会计调整问题。

上述来源支持通用框架，不为本产品的标签映射、默认参数或具体结论背书。

## 先还原财报，再计算指标

发行人通过 SEC 官方代码目录解析，不再限制四家公司。首批追加验证 AMD、AMZN、TSLA、META、GOOGL；每家公司的可用指标与模型能力单独检查。只使用 10-Q、10-K 及对应修订；不把 8-K 预测或管理层指引当成正式季度业绩。数据按实际起止日期匹配，不直接依赖容易混淆的 fiscal-year/frame 字段。

1. 有独立季度披露时优先采用该值。
2. 累计现金流或 Q4 收支，只在相同 XBRL 标签、相同财年起始日、相邻季度边界下差分。Q4 = 全年 − 前九个月。跨申报版本给出复核提示。
3. EPS 和加权平均股数不可用累计差分，缺失时显示 `—`。期末流通股数与期间加权平均股数分别保存。
4. TTM 必须有四个连续独立季度。资产负债表为时点余额，不能跨季度相加。
5. 使用最新可得修订值重建历史，**不是当时可知数据**，不能直接用于策略回测。
6. 申报目录和 Company Facts 可能不同步；标准标签未覆盖的分部、自定义标签、附注需要后续解析与人工复核。

每个指标保留 `value/status/formula/evidence`；证据含原值、单位、标签、起止日、提交日、表单类型、accession 和 SEC URL。原始文件记录 SHA-256、采集时间和缓存状态。归一化快照以内容摘要标识；估值绑定同一快照与报告期，避免前后输入串期。

## 财报分析公式

| 问题               | 计算                                              | 解释限制                                               |
| ------------------ | ------------------------------------------------- | ------------------------------------------------------ |
| 增长是否改善       | 本期 / 正值基期 − 1；分别比较上季、上年同季       | 净利润基期为零或亏损时不显示增长百分比，查看两期绝对值 |
| 盈利能力是否提高   | 毛利/收入、营业利润/收入、净利润/收入             | 同比变化使用百分点，需另查减值与一次性项目             |
| 现金能否覆盖投入   | 经营现金流 − 资本性现金支出                       | 这是常见现金流减资本支出口径，**不等于 FCFF**          |
| 利润能否变成现金   | 经营现金流 / 正值净利润，优先查看 TTM             | 存货、回款和付款时点会影响单季结果；不是质量评分       |
| 增长消耗多少资金   | 资本性现金支出 / 收入                             | 不直接推导投资回报，需要研究新增产能回报               |
| 偿债压力           | 总负债/总资产；流动资产/流动负债；已映射债务−现金 | 总负债不等于有息债务，现金不一定全部可用于偿债         |
| 每股结果是否被摊薄 | 本季加权平均稀释股数 / 上年同季 − 1               | 拆股、融资、回购、反稀释规则均需复核                   |

债务映射优先 `DebtCurrent + LongTermDebtNoncurrent`，避免重复计入流动到期部分。没有 DebtCurrent 时使用已披露长期债务流动/非流动部分和短期借款标签。称为“已映射账面有息债务”，不冒充完整市场价值。资本支出优先 PP&E，部分公司使用 ProductiveAssets，具体标签可点击查看。

三个置顶摘要由规则生成，标签为“计算事实 / 规则解读”。股数同比增加超过 3% 时优先提示股数变化；3% 是产品编辑阈值，不是学术确定的风险边界。没有黑箱综合评分、买卖评级或上涨概率。

## 基本面分析：五年 FCFF 模型

历史基线为所选季度截止的 TTM 收入和营业利润率。所有预测参数均显示为用户可修改假设。

```text
Revenue(t) = Revenue(t−1) × (1 + growth)
Margin(t) = 起点营业利润率 + (第五年目标利润率 − 起点利润率) × t/5
EBIT(t) = Revenue(t) × Margin(t)
OperatingTax(t) = max(EBIT(t), 0) × 假设税率
NOPAT(t) = EBIT(t) − OperatingTax(t)
NetReinvestment(t) ≈ max(Revenue(t) − Revenue(t−1), 0) / 销售资本比
FCFF(t) = NOPAT(t) − NetReinvestment(t)
```

经典 FCFF 为 `EBIT × (1−T) + 折旧摊销 − CapEx − Δ非现金营运资本`。本实现使用销售资本比近似净再投资，避免凭空分别预测折旧、资本开支和营运资本。收入下降时不自动假设资本释放；营业亏损时不计税收返还或 NOL 税盾。

```text
NOPAT(6) = NOPAT(5) × (1 + g)
稳定期再投资率 = g / 稳定期 ROIC
FCFF(6) = NOPAT(6) × (1 − g / 稳定期 ROIC)
TerminalValue = FCFF(6) / (WACC − g)
EV = Σ[t=1..5] FCFF(t)/(1+WACC)^t + TerminalValue/(1+WACC)^5
EquityResidual = EV + 非经营现金 + 其他非经营资产 − 债务 − 其他索偿
每股条件估值 = 正值 EquityResidual / 估值流通股数
条件安全边际 = 1 − 行情快照价格 / 每股条件估值
```

必须满足 WACC > g、稳定期 ROIC > g、股数 > 0。非正剩余股权价值不展示为负数目标股价；提示当前简单持续经营模型不适用。安全边际不同于预期上涨空间。最新报告期的比较价格绑定已核验的 Twelve Data 行情快照；无可用报价则不计算，历史报告期不联动当前行情。

默认：五年增长 8%、WACC 10%、税率 25%、g 2.5%、销售资本比 2、稳定期 ROIC 12%；目标利润率取历史 TTM 利润率并限制在 5%–65%；非经营现金与资产默认 0，债务/股数来自已披露映射，其他索偿初值使用可得少数股东权益账面差额。这些都是启动试算的假设，需研究后替换，不能称为市场预测。其他索偿与债务的完整性、市场价值及非经营现金范围需单独核实。

## WACC 与资本回报

```text
Ke = Rf + β × ERP
WACC = E/(D+E) × Ke + D/(D+E) × Kd × (1−T)
简化投入资本 = 已映射账面债务 + 含少数股东总权益 − 现金
平均投入资本 = (期末投入资本 + 上年同期期末投入资本) / 2
简化 ROIC = TTM 营业利润 × (1−假设税率) / 平均投入资本
资本回报差 = ROIC − WACC
```

WACC 权重 E、D 使用用户填写的**市场价值**，不是自动拿账面负债率替代。Rf、ERP、Kd 初值是教学示例；Beta 使用历史日线自动估计，股权市值按报价与已披露股数估算。ROIC 使用账面资本，是简化历史观察值；未进行研发资本化、租赁、商誉调整，非正资本或营业亏损期不输出该比例。历史 ROIC 与前瞻 WACC 比较只提供研究线索，不是买卖结论。

## 情景与敏感性

- 悲观/乐观在基准上分别调整增长 ±5 个百分点、目标利润率 ±3 个百分点、WACC ∓1 个百分点，受参数上下限约束。它们是机械压力情景，没有赋予发生概率，也不保证估值排序。
- 敏感性矩阵分别改变 WACC（±1/2 个百分点）与 g（±0.5/1 个百分点），其他输入不变；无效组合留空。
- 终值占 EV 超过 70%、WACC 与 g 相距不足 2 个百分点时提示敏感性。这是产品提示阈值。
- 固定 WACC、年末折现、五年利润率线性过渡；未计未来稀释、并购、复杂租赁、周期均值回归或研发资本化。银行、保险、REIT、早期亏损企业及加密资产需专门模型，不自动套用通用模型。

## 相对估值：P/E、P/B、P/S

参照 [CFA 相对估值框架](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples)，当前实现以下口径：

```text
估算市值 = 行情快照价格 × 拆股修正的最新已披露股数
P/E = 估算市值 / TTM 归属净利润
P/B = 估算市值 / 期末母公司账面权益
P/S = 估算市值 / TTM 营收
```

三个倍数使用行情快照与拆股修正已披露股数；DCF 共用快照价格，但股数允许独立情景调整。显示具体分子、分母、公式和来源。无可用报价时不计算；利润或权益非正时对应倍数不适用。市值/TTM 净利润口径不一定等于价格/已披露稀释 EPS，因为使用的股数和期间可能不同。当前未做优先股、复杂多类别股票、一次性利润、同业比较和历史分位调整，不用于判定绝对高估/低估。历史报告期暂停当前行情联动，不构成历史可交易信号。

## 历史 Beta 回归（手工导入工具）

用户提供按日期配对的资产与基准复权价格，至少 21 行价格形成 20 个收益率，最多 1500 行。价格必须为正，日期严格递增且不重复；数据来源与声明频率由用户核实。

```text
r_asset(t) = P_asset(t) / P_asset(t−1) − 1
r_market(t) = P_market(t) / P_market(t−1) − 1
Beta = Σ[(r_market−均值) × (r_asset−均值)] / Σ(r_market−均值)²
每期回归截距 = 平均资产收益率 − Beta × 平均基准收益率
R² = 协方差项平方 / (资产离差平方和 × 基准离差平方和)
```

这是带截距 OLS 的斜率，和协方差/方差定义一致。基准没有足够波动时拒绝计算；资产零波动时 R² 不适用。回归截距没有扣无风险收益，不能称为 Jensen alpha。Beta 可负；当前 CAPM UI 支持 0–5，超出时保留回归结果但禁用应用，不截断原估计。

基准、频率、窗口、复权处理和公司资本结构都会影响 Beta。它不是总风险或未来波动预测。手工 CSV 工具不独立验证来源；行情模块另行自动下载股票与 SPY 的拆股复权日线计算 Beta。自动 Beta 带入 CAPM，用户计算并应用 WACC 后改变 DCF。AI 只引用后端重算结果与样本摘要。

版本：`financials-1.0.0` / `fcff-sales-capital-1.0.0` / `beta-ols-1.0.0`。调整计算口径应升级版本并保留历史快照。

自动行情、拆股股数桥接、历史价格与 Beta 的具体口径及边界见 [行情数据接入](market-data.md)。
