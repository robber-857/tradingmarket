# Meridian 观澜 · AI 市场研究工作台

面向没有时间持续跟踪海外市场的个人用户，将美股与加密资产的宏观事件、研究观点、市场情绪与学习内容放在一个工作空间中。

**财报分析与基本面分析已连接 SEC 官方数据、Python 数学引擎和 OpenAI 解读服务。** 支持 SEC 官方目录按股票代码自动识别上市公司，获取可映射 US GAAP 发行人的财务证据、FCFF/DCF、CAPM/WACC、Twelve Data 报价与历史日线、自动 Beta、P/E/P/B/P/S、简化 ROIC，以及带引用的 AI 解读与追问。宏观日历已连接免费官方排期与数据。市场热点已连接公开新闻 RSS、Reddit 社区榜和带原文引用的 AI 解读，支持后台更新及每日目录；X 官方接口适配已实现，但尚未配置或验证。独立情绪页及多方观点仍为演示；总览已改为真实简报、新闻与官方事件汇总；账号后台、支付和公网部署尚未实现。

入口：[财报分析](http://127.0.0.1:5173/#financials) · [基本面分析](http://127.0.0.1:5173/#fundamentals)

全平台范围、功能状态与优先级：[总 PRD](docs/master-prd.md)。

首页已按现有布局接入已保存简报、官方排期和真实新闻，点击可进入对应详情；关注资产可继续财报、基本面或期权研究。首页不再显示模拟行情和情绪指数，也不会因打开页面重复调用 AI。验收见 [Homepage 记录](docs/validation-2026-11-10-homepage.md)。

规格与公式：[深度研究 PRD](docs/research-prd.md) · [财务与估值方法](docs/financial-methodology.md) · [AI 配置与校验](docs/ai-research.md) · [UI 与跳转逻辑](docs/research-ui-flow.md)

## 本地运行

需要 Node.js 20.19+ 或 22.12+、Python 3.12。以下命令适用于 Windows PowerShell。

```powershell
cd D:\tradingknowledge
npm ci
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server/requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 中配置 `SEC_USER_AGENT=应用名/版本 联系邮箱`；已有本机配置请保留。启用 AI 解读还需填写以下配置，均只在后端读取，不能加 `VITE_` 前缀：

```dotenv
OPENAI_API_KEY=在本机填写密钥
OPENAI_MODEL=gpt-5.4-mini
TWELVE_DATA_API_KEY=在本机填写行情密钥
```

保存后点击页面「检查 AI 配置」即可生效。配置好不代表账户额度或模型权限已验证；只有点击生成或发送才调用 OpenAI。没有 Key 时财报与数学计算仍可使用。密钥不要发送到聊天或提交版本控制。

分别在两个终端启动：

```powershell
npm run api
```

```powershell
npm run dev -- --port 5173 --strictPort
```

打开 http://127.0.0.1:5173 。前后端仅绑定本机；Vite 将 `/api` 代理到 `127.0.0.1:8001`。接口说明：http://127.0.0.1:8001/docs 。Python 文件修改后重启 API 服务。

```powershell
npm run build
npm run preview -- --port 4173
```

生产构建输出在 `dist/`。使用静态服务器托管，不能直接通过文件协议打开。研究页面还需要 Python 后端；生产部署须配置 `/api` 反向代理、认证、持久化和访问限制，不能只上传 `dist/` 后就宣称完整上线。页面采用 hash 导航。Google Fonts 不可用时回退到本机字体。

## 已实现的页面与交互

| 页面         | 已实现                                                                                                                 |
| ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| 市场总览     | 已保存简报、官方宏观关注、真实新闻、来源状态与自选研究入口                                                           |
| 市场热点     | 真实新闻 RSS、主题/时间/关键词筛选、Reddit 社区 Top(day)、每日目录、来源状态、AI 摘要与影响追问、原文链接；可选 X 样本接口 |
| 每日市场简报 | 每日 08:00 悉尼自动生成、事件/影响/风险提炼、原文引用、持久化历史、当天去重与失败恢复 |
| 宏观与事件   | 真实 CPI / 非农 / PCE / FOMC；来源、修订口径、时区转换、前值/实际值；可选一致预期、AI 解读与追问 |
| 多方观点     | 团队、分析师和经济学家虚构样本的观点与分类占比对照                                                                     |
| 市场情绪     | 虚构帖子、中英文解读、分类筛选、关键词添加/删除与方法说明                                                              |
| 财报分析     | 动态代码目录与真实 SEC 数据；近八季选择、三类重点摘要、季度与 TTM 指标、三表对比、净利润同比环比、来源弹层、证据 JSON 导出   |
| 基本面分析   | TTM 基线、简化 ROIC、五年 FCFF、CAPM/WACC 解释器、三情景、敏感性、逐年计算账本与 JSON 导出                             |
| 期权分析     | Nasdaq 延迟链、股票搜索、到期日分布、Put/Call 比、BSM IV / Greeks、CRR 比较、跨式成本、异动筛选、预计财报日历、AI 追问 |
| 期权策略     | 真实期权链选合约、十一模板、最多四组合盈亏与 Greeks、费用和报价口径、AI 解读追问；保留教学模式 |
| 我的关注     | 搜索添加、移除、刷新保留、跳转研究资产                                                                                 |
| 交易学院     | 三门文字样课、分类、课文阅读、学习完成状态、编辑并本地发布文章                                                         |
| 偏好与数据源 | 本地偏好保存、已集成 SEC 与待接入来源说明；订阅与个人空间说明                                                          |

支持桌面和移动端；全局搜索支持 Ctrl/Cmd+K，弹窗支持 Escape 与焦点约束。页面、图表、抽屉和课程缩略图有适度动效，并遵循 reduced-motion 系统偏好。

BTC、ETH 不套用公司财报。观点占比不等于上涨概率。提醒为本地标记，**不会**自动推送或发送邮件。课程发布不涉及互联网发布。宏观日历支持美东、北京、悉尼时区，并自动处理夏令时。

## 文件结构

- `src/App.jsx`：页面、导航、研究流程、弹窗与本地状态。
- `src/ResearchWorkspace.jsx` / `src/research.css`：真实财报与估值页面。
- `src/data.js`：与界面分离的模拟行情、财务、事件、研究文章和课程。
- `src/styles.css`：设计系统、布局、响应式规则与动效。
- `server/sec.py`：官方数据请求、节流、原始缓存与采集记录。
- `server/financials.py`：报告期匹配、单季还原、财务指标、证据和规则摘要。
- `server/valuation.py`：参数验证、FCFF、WACC、情景与敏感性。
- `server/app.py`：FastAPI 服务与绑定快照的计算接口。
- `server/market.py` / `src/MarketResearch.jsx`：行情、历史价格、自动倍数与 Beta、数据状态和快照。
- `server/narrative.py`：OpenAI Responses、证据账本、引用/数字校验及上下文绑定会话。
- `server/news.py` / `server/news_ai.py` / `src/NewsWorkspace.jsx`：新闻与社区采集、后台更新、每日目录和有来源的 AI 解读。
- `src/AIResearch.jsx` / `src/ResearchTools.jsx`：AI 追问、引用、倍数、Beta 与指标地图。
- `server/tests/`：数学、数据口径、API 及真实缓存对账测试。
- `server/cache/`、`server/reports/`：本机缓存与证据快照，均不入库；迁移时按需备份。
- `docs/product-scope.md`：产品边界与后续真实数据版本的实施拆分。
- `output/playwright/`：浏览器验证截图与导出样本（不纳入版本控制）。

## 股票搜索扩展

研究页和全局搜索均连接 SEC 官方代码目录，支持代码/英文公司名、大小写与 BRK.B/BRK-B 别名。目录匹配后按 CIK 下载财报，首次访问的新公司无需手工配置。银行、基金、20-F/IFRS、多上市证券和缺失标签会明确提示适用限制，目录命中不等于所有指标都能计算。详见 [动态股票研究](docs/stock-discovery.md)。

## 行情接入

基本面最新报告期自动获取 Twelve Data 报价、股票及 SPY 历史日线，不再要求手填价格。详情、公式、授权范围和缓存策略见 [行情数据接入](docs/market-data.md)。密钥保存后点击「刷新行情」；首次请求通常约半分钟，后续使用缓存。价格只在进入页面或手动刷新时更新，不是逐笔流。

## 验证记录

2026-11-09 深度研究版本：

```powershell
npm run test:finance
npm run build
```

宏观接入验证：160 项测试通过，生产构建通过。包含 AI 输出校验、会话隔离、模型异常、Beta 回归和相对估值，以及原有财报与估值测试。测试客户端有一项 Starlette/httpx 弃用提示。

已使用配置的真实 OpenAI API 验证财报解读、连续追问与基本面解读，默认模型为 gpt-5.4-mini。浏览器验证 AI 引用弹层、研究 JSON 导出、指标→追问跳转、Beta→CAPM→WACC 参数传递、跨页报告期保持及 390px 手机布局。模拟 429 时保留先前成功答案；修改估值参数后旧会话清空。测试中发现的 TTM/累计口径、裸内部 ID 与假设分类问题已增加保护；格式校验不保证所有推论正确，仍需人工复核。

财务测试覆盖累计差分、Q4、非加总指标、负基期、缺失、修订、债务去重、独立 DCF 算例、终值约束、WACC 权重与快照匹配。真实缓存对账测试在没有本地下载数据时会跳过；合成算例测试不依赖网络。

浏览器已核验公司/期间切换、Q4 来源弹层、三表切换、行情自动价格、WACC 计算与应用、无效参数恢复、计算 JSON 导出，以及 1440×1080 / 390×844 两种尺寸的页面溢出检查。模拟接口 503 时隐藏旧分析并显示错误，重试后恢复；无效 WACC 的 422 和该模拟 503 是验收预期响应。截图及导出样本保存在 `output/playwright/`。以上是本地验收，不代表公网部署或金融结论已完成第三方审计。

数据边界：最新可得修订口径不是当时可知数据；账面债务映射不代表所有索偿完整；预测参数是用户假设；缺少一致预期或指引全文时不输出超预期判断或涨跌归因。

2026-11-08：

- `npm run build` 生产构建通过。
- 初始安装的 npm audit 为 0 个已知漏洞。
- Playwright 检查 1440×1000 和 390×844 下全部 10 个页面，无页面横向溢出。
- 验证连续资产输入、财报三表切换、成长预期和加密资产财报分流。
- 验证本地课程发布、刷新保留、课程阅读与学习完成状态。
- 验证事件提醒清单、事件详情、已公布筛选、情绪关键词添加/移除与分类。
- 验证移动端菜单、全局搜索结果与空状态、关注刷新保留、简报下载。
- 测试新增课程与关键词已清理，未清空既有用户数据。

## 设计依据

当前视觉采用 Lightness / Darkness 双主题，保留侧栏、摘要区与双栏研究布局。核心工作流是「首页每日关注 → 事件与来源 → 资产研究 → 学习」。早期 Dribbble 参考继续作为布局与交互依据。

参考了用户指定的设计方向，未复制其素材：

- [Untitled UI 侧边导航](https://dribbble.com/shots/25709086-Sidebar-navigation-Untitled-UI)
- [Team Communication Management SaaS Dashboard](https://dribbble.com/shots/25526476-Team-Communication-Management-SaaS-Dashboard)
- [Shopeers Analytics Dashboard](https://dribbble.com/shots/26628350-Shopeers-AI-Powered-B2B-eCommerce-Analytics-Dashboard)

## 免费宏观日历

访问 `http://127.0.0.1:5173/#calendar`。默认免费官方模式，无需新增数据 API Key。CPI / 非农使用 BLS 公共 API 与美国劳工部转载新闻稿；PCE 使用 BEA 新闻稿和排期；FOMC 使用美联储日历和声明。

官方来源不提供市场一致预期，缺失时显示“暂无预期”，AI 不会据此判断超预期。需要调查预期时，可选配置 `.env` 中的 `TRADING_ECONOMICS_API_KEY`；它不是免费模式的前置要求。现有 OpenAI API 仍按实际用量计费。

详见 [宏观来源与方法](docs/macro-data.md)。

## 真实市场热点

访问 [市场热点](http://127.0.0.1:5173/#news)。CNBC、CoinDesk、Cointelegraph、美联储和 SEC 的公开 RSS 无需新增 Key；Reddit 使用五个指定社区的公开 Top(day) RSS，可能限流，不能代表全站热榜。AI 使用已有 OpenAI 配置，按用量收费。可选 X 官方访问配置为后端 `.env` 中的 `X_BEARER_TOKEN`，不是免费新闻功能的前置条件。

后端启动时及每 30 分钟采集，按悉尼日期保存滚动 24 小时新闻目录；关闭后端或电脑后不会继续运行。历史目录保留 30 天，AI 仅点击时生成，不自动发送通知。详见 [来源、更新与开源技能选择](docs/market-news.md) 和 [本地验证记录](docs/validation-2026-11-09-news.md)。新闻版本：187 项测试通过，生产构建通过。

## 每日简报与期权研究

新增 [每日市场简报](http://127.0.0.1:5173/#daily)、[期权分析](http://127.0.0.1:5173/#options)、[期权策略](http://127.0.0.1:5173/#strategies)。

每日简报默认每天 08:00 悉尼时间自动使用已有 OpenAI 生成，按用量收费，并保存 SQLite 历史。`.env` 可配置 `DAILY_BRIEF_ENABLED=1` / `DAILY_BRIEF_HOUR=8`；成功后当天不重复生成。后端停止则任务停止。市场热点里的单条分析仍为按需调用。

期权默认使用无需新增 Key 的 Nasdaq 公开延迟链与预计财报日历。买卖价差过大或缺失时不反推 IV；OI 不代表买卖方向，跨式成本不是财报方向预测。利率和股息率为明确标注的可调整模型假设。策略页现在默认连接真实链，可选择到期日和合约，按买 Ask / 卖 Bid 或中间价比较最多四个组合的盈亏、Greeks 和风险，并支持 AI 解读及追问。原有教学示例保留在独立标签页。

实现与公式见 [每日简报与期权说明](docs/daily-brief-options.md)。2026-11-10 本地测试 220 项通过，保留一项既有 Starlette/httpx 弃用提示；验证记录见 [本地验收](docs/validation-2026-11-10-daily-options.md)。

真实策略扩展的公式、单位、报价与限制见 [真实期权策略](docs/live-option-strategies.md)。最新版本 237 项测试及构建通过；真实 AAPL/NVDA、OpenAI 解读追问及手机布局的记录见 [策略扩展验收](docs/validation-2026-11-10-live-strategies.md)。
