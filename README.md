# 霁明 Clarora · AI 市场研究工作台

<img src="public/clarora-mark.svg" alt="霁明 Clarora 品牌标志" width="88" />

**云销雨霁，万象澄明。研究有据。**

面向个人研究者的美股、加密资产与宏观研究工作空间。将市场总览、新闻、官方经济发布、公司财报、估值和期权研究连接起来，保留数据来源、计算假设与 AI 引用，帮助用户形成自己的判断。

> 文档更新：2026-11-10。以下描述仓库已提交版本的能力。本项目目前以本机运行与验证为主，不代表已部署公网服务；账号后台、支付、跨设备同步和邮件推送尚未实现。

## 功能与数据状态

| 模块 | 当前能力 | 使用边界 |
| --- | --- | --- |
| 市场总览 | 已保存简报、近期宏观事件、最近 24 小时新闻、自选市场行情和研究入口 | 首页读取已有结果，不因打开页面重复生成 AI 简报；行情为参考数据 |
| 市场热点 | 公开 RSS、Reddit 社区榜、主题/时间/关键词筛选、列表分页、悉尼日期归档、AI 解读与追问 | 分析依据摘要或帖文预览，不代表阅读全文或全网覆盖；X 接口适配尚未配置验证 |
| 每日市场简报 | 默认悉尼时间 08:00 自动生成，保留引用、SQLite 历史、当天去重及中断恢复入口 | 后端持续运行时才执行；使用 OpenAI 额度，不发送推送通知 |
| 宏观与事件 | CPI、非农、PCE、FOMC 官方排期和实际值，时区切换、修订提示、公开预测及机构观点、中文翻译和 AI 解读 | 调查、机构预测、模型预测分开标注；没有可匹配来源时留空 |
| 财报分析 | SEC 动态代码目录、报告期选择、季度/TTM 指标、三表、来源追溯和 JSON 导出 | 仅计算能可靠映射的披露；目录命中不保证全部指标可用 |
| 基本面分析 | FCFF/DCF、CAPM/WACC、简化 ROIC、三情景、敏感性、计算账本、Twelve Data 行情及 Beta | 预测参数为假设；报价、财报时间与模型适用限制独立标注 |
| 期权分析 | Nasdaq 延迟期权链、到期日分布、Put/Call、IV/Greeks、CRR 对照、跨式成本、异动线索和预计财报日历 | 不保证合约报价同时更新；价差过大或报价缺失时不反推 IV |
| 期权策略 | 真实链选合约、十一种模板、最多四个组合对比、盈亏与 Greeks、费用及报价口径、AI 追问；保留教学模式 | 不保证参考价格可成交；模型未涵盖全部实际交易风险 |
| 我的关注 | 添加/删除资产、浏览器内保存、真实参考报价、前收盘涨跌幅、近月走势、来源链接与研究跳转 | 页面可见时每 5 分钟检查；失败时标注上次报价，缺失不补零；参考行情可能延迟 |
| 市场情绪、交易学院 | 情绪示例、文字样课、学习进度和本地文章编辑 | 情绪为演示；文章仅本地保存，公开发布未开放 |
| 偏好与品牌 | 浅色/深色主题、移动端布局、本地偏好、产品说明、新版霁明 Clarora Logo | 本地记录不跨设备同步 |

首页市场行情可选 Nasdaq 100、标普 500、黄金/白银期货、BTC、美国十年期国债收益率、美元指数与 VIX。来源为 Yahoo Finance 公开 chart 接口；显示报价时间、前收盘变化、近月日线与来源状态。它与公司研究中的 Twelve Data 行情是不同数据通道。详见 [总览行情口径](docs/dashboard-markets.md)。

### 我的关注：真实参考行情

自选列表通过 `GET /api/market/watchlist?symbols=NVDA,BTC,SPX` 读取 Yahoo Finance 公开 chart 数据，替换原有模拟价格和走势。支持普通股票代码、`BRK.B` / `BRK-B`，以及 `SPX`、`NDX`、`BTC`、`ETH` 的来源代码映射。指数价格单位为点，其余展示 USD；BTC / ETH 涨跌基准为前一 UTC 日收盘。

- 单次最多 50 个去重代码；页面对更长清单分批请求。每批最多并发 6 个来源请求，服务端缓存最长 5 分钟，手动刷新也可能读取有效缓存。
- 单个资产来源失败不会抹掉其他资产结果；有旧缓存则标注更新失败及原报价时间，无缓存则显示空值。接口整体失败时页面保留旧报价并提示重试。
- 手机端保留价格、涨跌、来源链接和删除按钮，隐藏走势图以节省空间。删除只修改当前浏览器的关注清单，刷新后仍保留。
- 首次进入及手动刷新会请求数据；定时检查仅在页面可见时执行。不提供逐笔推送，也不保证源站可用。

## 本地运行

需要 Node.js 20.19+ 或 22.12+、Python 3.12。以下命令适用于 Windows PowerShell，在项目根目录执行。

```powershell
cd D:\tradingknowledge
npm ci
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server/requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

保留已有 `.env`，不要覆盖本机密钥。根据需要填写：

| 配置项 | 用途 |
| --- | --- |
| `SEC_USER_AGENT` | SEC 请求使用的应用名称/版本和联系邮箱 |
| `OPENAI_API_KEY`、`OPENAI_MODEL` | AI 解读、追问、翻译与每日简报；示例默认模型为 `gpt-5.4-mini` |
| `TWELVE_DATA_API_KEY` | 公司研究行情、历史日线与 Beta |
| `TRADING_ECONOMICS_API_KEY` | 可选付费调查预期；不是官方宏观数据的前置要求 |
| `X_BEARER_TOKEN` | 可选官方 X 接口；不是 RSS 新闻和 Reddit 的前置要求 |
| `DAILY_BRIEF_ENABLED`、`DAILY_BRIEF_HOUR` | 默认 `1`、`8`，按 `Australia/Sydney` 调度 |

这些配置只在后端使用，**不能加 `VITE_` 前缀，也不要提交密钥到 Git**。配置存在不等于额度、权限或实时调用已经验证。关闭自动 AI 简报可设置 `DAILY_BRIEF_ENABLED=0`；新闻与财报等非 AI 数据功能仍按各自来源工作。

### 固定两个服务端口

只保留一个前端 `5173` 和一个后端 `8001`。分别在两个终端启动：

```powershell
# 终端一：后端
npm run api
```

```powershell
# 终端二：前端，端口占用时直接报错，不自动切换到 5174
npm run dev -- --port 5173 --strictPort
```

- 网站：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- 后端接口文档：[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)
- Vite 将 `/api` 代理到 `127.0.0.1:8001`；浏览器应访问前端地址。
- 修改 Python 代码后重启后端。终端启动的服务可用 `Ctrl+C` 停止，再重新运行。
- 服务仅绑定本机。关闭服务或电脑后，新闻更新、公开预测采集及每日简报调度不会继续执行。

### 连接检查与构建

```powershell
# 两项都应返回 status: ok，第二项同时检查前端代理
Invoke-RestMethod http://127.0.0.1:8001/api/health
Invoke-RestMethod http://127.0.0.1:5173/api/health

# 检查两个固定端口的占用进程
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 5173,8001 } |
  Select-Object LocalAddress,LocalPort,OwningProcess

npm run build
```

页面打不开时先确认 `5173` 正在监听；页面能打开但数据失败时检查 `8001` 与前端代理。端口被占用时先核实进程所属项目，不要重复启动或停止其他项目的服务。健康检查通过仅说明服务可达，不保证外部数据源或 AI 服务均可用。

构建输出在 `dist/`，不能直接以文件协议打开。若需预览生产构建，先停止开发前端，再运行 `npm run preview -- --port 5173 --strictPort`，后端仍保留 `8001`。公网部署还需配置 `/api` 反向代理、认证、持久化与访问限制；仅上传静态文件不能提供完整功能。

## 来源、调度与研究边界

- **财报**：SEC 官方披露；保留来源、报告期、获取时间和修订口径。银行、基金、20-F/IFRS 等可能存在适用限制；BTC、ETH 不套用公司财报模型。
- **宏观**：BLS、BEA、美联储等官方发布；公开预测包括 Scotiabank、RBC、U.S. Bank 与 Cleveland Fed。机构预测、模型预测不冒充市场一致预期，历史回补不冒充公布前已知信息。详见 [宏观来源](docs/macro-data.md) 与 [公开预测及机构观点](docs/public-forecasts.md)。
- **新闻**：公开 RSS 与指定 Reddit 社区榜。默认后端启动时及每 30 分钟采集，按悉尼日期归档，历史目录保留 30 天。来源可能限流或失效，保留旧数据时明确标注。详见 [市场新闻](docs/market-news.md)。
- **AI**：多数解读和追问按需调用，首次机构观点翻译也可能调用 AI；每日简报默认另有自动调度。引用与格式校验不能保证全部推论正确，仍需核对原文。
- **期权**：延迟报价、OI 与跨式成本不是方向预测或真实胜率；不把缺失数据补成零。详见 [每日简报与期权](docs/daily-brief-options.md)、[真实期权策略](docs/live-option-strategies.md)。
- **授权与持久化**：公开可访问不等于获得商业再分发许可。浏览器关注、偏好与学习记录不跨设备同步；本机缓存和简报历史需要另行备份。

## 测试与验证

```powershell
# 前端数据逻辑及用户错误提示
node --test tests/*.test.mjs

# 后端数据、计算、API 与证据校验
npm run test:finance

# 生产构建
npm run build
```

如果受限环境无法创建系统临时目录，可为 pytest 指定项目内一个新的临时目录，例如：

```powershell
.venv\Scripts\python.exe -m pytest server/tests -q --basetemp=output/pytest-check-001
```

`--basetemp` 目录只用于测试，不要指向需保留的文件夹。部分真实缓存对账测试在没有本机数据时会跳过；自动化测试不等于实时数据源验证。

2026-11-10 自选行情更新：**14 项前端测试、282 项后端测试通过，生产构建通过**。测试覆盖代码映射与去重、缓存过期和隔离、部分来源失败与旧报价、非法代码及接口长度限制。浏览器验证真实报价、手机布局、删除及刷新持久化、模拟 503 时保留旧数据与重试恢复。后端仍有一项既有 Starlette/httpx 弃用提示。此前 Logo 更新已检查桌面、390px 手机和深色主题显示。上述为本地验收，不代表所有外部数据源持续可用或已通过线上验收。

专项记录：[首页](docs/validation-2026-11-10-homepage.md) · [财报与 AI](docs/validation-2026-11-09-ai.md) · [每日简报与期权](docs/validation-2026-11-10-daily-options.md) · [真实策略](docs/validation-2026-11-10-live-strategies.md)。这些记录对应各自阶段，测试数量和覆盖范围可能不同。

## 代码与文档导航

| 路径 | 内容 |
| --- | --- |
| `src/App.jsx` | 导航、页面组合、本地状态与弹窗 |
| `src/BrandMark.jsx`、`public/brand/clarora-approved.png` | 已确认品牌原图及展示组件；英文和中文装饰保留原稿 |
| `src/HomeOverview.jsx`、`src/DashboardMarkets.jsx` | 首页汇总、参考行情与分页 |
| `src/Watchlist.jsx`、`src/watchlist.css`、`server/dashboard_market.py` | 自选资产参考行情、缓存与响应式列表 |
| `src/ResearchWorkspace.jsx`、`src/MarketResearch.jsx` | 财报、估值、行情研究 |
| `src/NewsWorkspace.jsx`、`src/MacroCalendar.jsx` | 新闻与宏观事件 |
| `src/DailyBrief.jsx`、`src/OptionsWorkspace.jsx`、`src/LiveStrategies.jsx` | 每日简报、期权链和组合研究 |
| `src/customer-message.js`、`src/product-polish.css` | 用户错误提示与界面细节 |
| `server/app.py` | FastAPI 接口与后台任务生命周期 |
| `server/sec.py`、`server/financials.py`、`server/valuation.py` | 财报采集、指标和估值引擎 |
| `server/narrative.py` | OpenAI 调用、证据与引用校验 |
| `server/tests/`、`tests/` | 后端及前端逻辑测试 |
| `server/cache/` 等忽略目录 | 本机缓存、简报数据库、报告和研究快照，不提交 Git |
| `output/` | 本地验证截图、测试临时文件与运行日志，不提交 Git |

产品与方法：[总 PRD](docs/master-prd.md) · [深度研究 PRD](docs/research-prd.md) · [财务与估值方法](docs/financial-methodology.md) · [股票搜索](docs/stock-discovery.md) · [行情接入](docs/market-data.md) · [AI 配置](docs/ai-research.md) · [研究交互](docs/research-ui-flow.md)。

品牌已从 Meridian / 观澜更新为 **霁明 Clarora**。代码中保留部分 `meridian.*` 浏览器存储键，以延续已有本地偏好。界面使用浅色/深色主题，兼容移动端和减少动态效果的系统偏好。
