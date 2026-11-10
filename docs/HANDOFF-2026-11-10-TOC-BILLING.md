# 霁明 Clarora：开发迁移与接续

更新：2026-11-10（Australia/Sydney）。目录：`D:\tradingknowledge`。本文件用于换聊天继续开发；数据库 / 云端迁移状态单列，不表示已执行远程迁移。

## 1. 先读与边界

阅读顺序：[文档目录](README.md) → [总 PRD](master-prd.md) → [ToC P0](toc-launch-p0.md) → [测试支付](test-payments.md)。

- 产品名为霁明 Clarora，旧 `meridian.*` 浏览器存储键保留兼容。
- 仅 ToC 与测试支付；不做 ToB，不开启正式收款，不把模拟测试当作实际沙盒成功。
- 保留所有已有未提交改动，不执行 reset / clean，不删除数据库、缓存或未跟踪文件。
- 用户已确认另一个聊天正在修改同一工作区的云端迁移。**本次仅提交整理后的文档，会员及迁移代码不纳入本次提交。** 后续先检查最新 Git 状态与并行修改。
- 不输出或提交 `.env`、密钥、数据库、真实订单或一次性登录链接。管理员邮箱仅保留在私有配置。

## 2. 已完成的本地功能

| 模块 | 当前实现 | 边界 |
| --- | --- | --- |
| 会员与账户 | 邮箱一次性登录、HttpOnly 会话、用户隔离、免费 / 研究 / 高级 / 专家、七天通行证 | 生产 SMTP 未验证；固定三币种试定价，正式售卖关闭 |
| 会员 UI | 浅 / 深色三张付费卡、免费与七天辅助入口、紧凑账户额度区；方案 / 付款账单 / 研究记录三个分区 | 市场情绪不作为当前可用权益出售；无年付假折扣 |
| 交易学院 | 恢复原横幅、分类、卡片、阅读弹窗和本地文章；会员正文服务端鉴权 | 活跃实现是 `src/App.jsx` 的 `renderAcademy`；`src/Academy.jsx` 不是当前入口；样课不代表正式课程已交付 |
| AI 与保存 | 五类 AI 界面提供普通 / 深度切换；成功记账、失败释放、请求幂等；财报 / 估值账户归档，自选手动保存 / 读取 | pending 恢复、完整策略 / 会话恢复、自动同步冲突处理待做 |
| 账号后台 | `/#admin` 按邮箱建账号、1–366 天限时会员、撤销、用量与审计 | 整段有效期只有一份套餐额度；不覆盖未结束权益、不授予普通用户管理员身份 |
| 支付运营 | 无密钥配置检查、待确认订单分页、带原因和审计的渠道核对 | 不自动 capture、不人工置为 paid；缺渠道编号须排查原请求，无自动扫描或拒付闭环 |

普通与深度共用 `OPENAI_MODEL`，默认 `gpt-5.4-mini`。深度采用 high / 10000 tokens，普通默认 medium / 6000（宏观普通 low）；增加反例、敏感性和证伪检查，不换模型、不额外全网搜索。每次追问按所选模式只扣对应 bucket。没有新增真实模型质量 / 成本评测。

账号管理员：`CLARORA_ADMIN_EMAILS` 或 `CLARORA_ADMIN_USER_IDS`；退款管理员：`BILLING_ADMIN_USER_IDS`，配置账户 ID 而非邮箱，两类权限分开。见 [账号后台](admin-accounts.md)。

## 3. 支付规则与配置缺项

| 渠道 | 币种 / 周期 | 续费 |
| --- | --- | --- |
| Stripe 银行卡 / Apple Pay | AUD、USD；月度或七天 | 月度自动续费；七天单次；Apple Pay 取决于商户和设备条件 |
| Stripe 支付宝 | CNY；月度或七天 | 单次，到期手动续购 |
| 独立 PayPal Sandbox | AUD、USD；月度或七天 | 单次，到期手动续购，未做自动订阅 |

服务端校验原始 webhook 签名，并重新读取渠道对象核对身份、金额与币种，幂等发放权益。浏览器返回页不能开通。Stripe 取消自动续费后保留已付周期，续费成功才发新周期；中途切币 / 换档禁止。

退款按每笔付款：七天内且未使用该笔权益可申请，先冻结，审核后全额原路退回；渠道成功才永久撤销，审核拒绝恢复原时间和额度。成功 AI、pending AI、付费课正文算使用；失败 AI、免费课、历史记录和公共简报阅读不算。外部部分退款冻结并转人工，拒付争议流程待补。

**最近配置检查仍缺失，测试开关关闭；没有实际 Stripe / 支付宝 / PayPal Sandbox 付款或退款，没有正式收款。** 后续先重新检查，不能假设用户尚未补填：

```powershell
.venv\Scripts\python.exe -X utf8 -m server.payment_operations
```

该 CLI / `/api/admin/billing/readiness` 只报告配置存在性与格式，`credentialsVerified` / `webhookDeliveryVerified` 仍为 false；配置齐全不等于账户和回调已验证。

| 配置项 | 用途 |
| --- | --- |
| `BILLING_TEST_ENABLED` | 测试支付开关；当前关闭 |
| `STRIPE_TEST_SECRET_KEY`、`STRIPE_TEST_WEBHOOK_SECRET` | 测试 API、回调验签 |
| `STRIPE_TEST_PORTAL_CONFIGURATION` | 测试订阅门户 |
| `PAYPAL_SANDBOX_CLIENT_ID`、`PAYPAL_SANDBOX_CLIENT_SECRET`、`PAYPAL_SANDBOX_WEBHOOK_ID` | Sandbox API 与回调 |
| `BILLING_ADMIN_USER_IDS` | 退款审核账户 ID，与账号管理独立 |
| SMTP 与发件人配置 | 生产登录投递另行配置 / 验收，不与支付混淆 |

Stripe 固定 API `2024-06-20`，拒绝 live key；PayPal 固定 sandbox 地址。支付宝经 Stripe Alipay，不需另填国内支付宝密钥，但通道资格待确认。回调为 `/api/billing/webhooks/stripe` 和 `/api/billing/webhooks/paypal`；PayPal 需可达的测试 HTTPS 环境，不直接把 local 开发登录暴露到公网。详见支付配置文档。

## 4. 关键代码入口

| 文件 | 职责 |
| --- | --- |
| `server/membership.py` / `server/member_api.py` | 会员目录、账户、权益、额度、保存、来源检查与计量中间件 |
| `server/academy.py` / `server/academy-courses.json` | 课程目录、正文授权、付费阅读记录 |
| `server/admin_api.py` | 手动开通、撤销、权限与审计 |
| `server/billing_catalog.py` / `server/billing_engine.py` | 报价、订单、付款、权益与退款状态 |
| `server/payment_providers.py` / `server/billing.py` | 测试渠道、回调、主动核对、取消、门户、退款 API |
| `server/payment_operations.py` | 配置检查、待确认订单、只读渠道核对与审计 |
| `src/Membership.jsx` / `src/membership-design.css` / `src/BillingPanel.jsx` | 会员卡、主题、付款与账单；当前选择须与服务端报价匹配 |
| `src/Admin.jsx` / `src/PaymentOperations.jsx` | 账号与支付运营 UI |
| `src/AnalysisDepth.jsx` / `src/AIResearch.jsx` | 模式切换、财报 / 估值保存；其他研究组件复用选择器 |
| `src/SavedResearch.jsx` / `src/WatchlistSync.jsx` | 研究回读、自选手动同步 |
| `server/tests/test_membership.py` / `test_billing.py` / `test_admin.py` / `test_payment_operations.py` | 账号 / 额度 / 课程、支付、手动授权和运营测试 |

## 5. 启动与数据保护

前端固定 **5173**，后端固定 **8001**。先检查服务和进程所属项目；已有服务则复用，不自动换 5174，不按旧 PID 停止进程。

```powershell
cd D:\tradingknowledge
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 5173,8001 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
Invoke-RestMethod http://127.0.0.1:8001/api/health
Invoke-RestMethod http://127.0.0.1:5173/api/billing/status
```

确认服务未运行后，两个终端分别运行 `npm run api` 和 `npm run dev -- --port 5173 --strictPort`。Python 修改按实际启动方式重载，不与另一聊天同时重启。

本地已验证账号库默认 `server/cache/membership.sqlite3`，可由 `CLARORA_DATABASE` 指定。保留账号 / 会话 / 权益 / 用量 / 保存、付款 / 退款 / 回调、手动授权 / 审计数据；不通过删库重置测试。JSON 缓存、简报和研究快照同样保留。`output/` 截图 / 日志不进 Git。

`CLARORA_MODE=local` 只用于本机，匿名研究保留本地工作流，已登录计量；公网由迁移工作落实 public、HTTPS、SMTP、持久化和访问控制，不能仅上传静态页面。

## 6. 并行数据库 / 云端迁移

用户已确认另一聊天正在修改项目。当前工作区已出现 `server/database.py`、`server/schema.sql`、`server/object_store.py`、`server/session_store.py`、`supabase/migrations/` 及部署适配；多处研究缓存、账户和简报调用也在变化。文件存在不是迁移已执行的证据，本次不修改、暂存或提交这些代码，不执行远程 SQL、不部署。

迁移完成后必须补充：

1. 实际目标环境、数据库 / 存储供应商、部署方式与已应用迁移版本，不含连接串和密钥。
2. 所需环境变量名称、私有存储访问方式、schema 权限和 local / public 启动前置条件。
3. SQLite、JSON 和研究归档是否迁移；源端备份、校验计数、切换窗口和回退步骤。未导入不能写数据已迁移。
4. PostgreSQL 事务 / 隔离 / 幂等、私有对象访问、会话过期 / 跨实例、任务去重、备份恢复的实际验证。
5. 本地兼容回归与真实部署验收分别记录，348 项旧测试不能覆盖新修改。

提交前检查 `git status --short`、`git diff --cached --name-only` 和分支 / 远程状态，只提交核对过的明确文件，不用 `git add .` 包入另一聊天的半成品。仓库 `origin` 为 `https://github.com/robber-857/tradingmarket.git`，本次整理开始时在 `main`；最终提交状态以 Git 日志为准。

## 7. 验证证据与命令

迁移开始前的最近完整本地验收：后端 **348 passed**、前端 **14 passed**，生产构建通过，浏览器无错误；支付专项 37 项包含在后端集合内，不相加。会员在 390、768、1440px 及浅 / 深色检查，手机付款页无横向溢出；验证三币种报价、缺配置禁用结账和管理员隔离。详见 [验收记录](validation-2026-11-10-membership-billing-v2.md)。

旧阶段 294 / 317 / 338 等结果保留在历史记录中，不替代最新结果。本次文档整理未重新验证正在变动的迁移代码；未验证真实 SMTP、实际渠道付款 / 退款、Apple Pay 设备、云端压力或新模型质量。

```powershell
node --test tests/*.test.mjs
.venv\Scripts\python.exe -m pytest server/tests -q --tb=short --basetemp=output/pytest-handoff-UNIQUE
npm run build
git diff --check
```

`UNIQUE` 换成新的专用目录；pytest 会清理该目录，绝不能指向数据库、历史截图或其他有用输出。

## 8. 接下来做什么

1. 读取当前代码 / Git，与并行修改边界对齐，完成迁移专属验证与交接。
2. 重查测试配置；齐全后实际沙盒付款、回调 / 核对、续费失败 / 成功、取消、退款和重复通知，逐笔对账。
3. 配置缺失时继续无外部账户依赖的 P0：缺渠道编号恢复、拒付、AI pending 恢复、token / 成本统计与费用保护。
4. 完成商业授权、生产邮件、备份恢复、完整研究保存和正式课程；市场情绪未接供应商前关闭能力与扣费。
5. 正式上线另行验收和授权，当前只测试支付、不做 ToB。

可贴到新窗口：

> 请先阅读 docs/README.md、docs/HANDOFF-2026-11-10-TOC-BILLING.md、docs/toc-launch-p0.md 和 docs/test-payments.md。检查并保留 D:\tradingknowledge 的所有未提交改动；另一聊天正在修改数据库和云端迁移，先确认当前状态，避免交叉覆盖。继续霁明 ToC P0，仅测试支付、不正式收款、不做 ToB。配置只报告缺项，不输出密钥；齐全后实际沙盒联调，缺失继续无账户依赖任务。前端 5173、后端 8001，启动前检查已有服务。
