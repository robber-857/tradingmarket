# 霁明 Clarora：开发迁移与接续

更新：2026-11-10（Australia/Sydney）。目录：`D:\tradingknowledge`。本文件用于换聊天继续开发；数据库 / 云端迁移状态单列，不表示已执行远程迁移。

## 1. 先读与边界

阅读顺序：[文档目录](README.md) → [总 PRD](master-prd.md) → [ToC P0](toc-launch-p0.md) → [测试支付](test-payments.md)。

- 产品名为霁明 Clarora，旧 `meridian.*` 浏览器存储键保留兼容。
- 仅 ToC 与测试支付；不做 ToB，不开启正式收款，不把模拟测试当作实际沙盒成功。
- 保留所有已有未提交改动，不执行 reset / clean，不删除数据库、缓存或未跟踪文件。
- 另一聊天的迁移已完成并提交为 `69fc9e6`；独立复核发现的财报 S3 兼容问题已在 `fd871e8` 修复、推送并发布。股票搜索和 AAPL / MSFT 财报实测恢复，支付与自动 AI 简报继续关闭；后续先核对最新 Git 与部署版本。
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

确认服务未运行后，两个终端分别运行 `npm run api` 和 `npm run dev -- --port 5173 --strictPort`。Python 修改按实际启动方式重载；本次复核未重启 5173 / 8001。

本地已验证账号库默认 `server/cache/membership.sqlite3`，可由 `CLARORA_DATABASE` 指定。保留账号 / 会话 / 权益 / 用量 / 保存、付款 / 退款 / 回调、手动授权 / 审计数据；不通过删库重置测试。JSON 缓存、简报和研究快照同样保留。`output/` 截图 / 日志不进 Git。

`CLARORA_MODE=local` 只用于本机，匿名研究保留本地工作流，已登录计量；公网由迁移工作落实 public、HTTPS、SMTP、持久化和访问控制，不能仅上传静态页面。

## 6. 已完成迁移与本次复核

迁移提交：`69fc9e6`，包含业务依赖、PostgreSQL / 私有 S3、会话持久化、部署和 cron。公开站点为 `https://clarora-market-research.vercel.app`；私有配置 `.env.supabase.local` 不进 Git。完整资源、配置和回退见 [部署说明](vercel-supabase-deployment.md)。本地 SQLite 与云端不双向同步。

本次只读核对：19 张业务表中，16 张会员来源表及 1 张简报来源表与 SQLite 备份逐行一致；2 个用户、1 个会话、12 条限流记录、1 条简报保留。674 个 JSON 内容一致，1 个当天新闻归档已更新，3 个备份后本地新增对象尚未同步。私有 bucket 和业务 schema 权限符合预期；基础页面接口正常，匿名后台 / cron 返回 401。

**已发布缺陷修复**：此前股票目录 / 财报因 S3 `ObjectPath` 缺少 `read_bytes()` 返回 HTTP 500。修复 `fd871e8` 已发布至生产域名，AAPL / Microsoft 搜索和 AAPL / MSFT 八季财报均返回 200，快照与来源哈希正常。没有重跑导入或启用付款 / 自动 AI 简报。详见 [迁移复核](validation-2026-11-10-migration-audit.md)。

源备份在 `output/pre-supabase-20261110-180524/`。不重新导入非空云端库，不用旧本地数据覆盖云端新增内容。还需完成实际备份恢复演练、线上真实用户邮箱 / 权益流程、监控及负载验证。只读核对命令与报告见复核文档；它不会修复数据或触发模型 / 收款。

提交前检查 Git 状态与暂存区，明确区分本地修复和远端已部署版本。仓库为 `https://github.com/robber-857/tradingmarket.git`，当前使用 `main`；上线后核对部署 SHA，而非只看 health。

## 7. 验证证据与命令

迁移开始前的最近完整本地验收：后端 **348 passed**、前端 **14 passed**，生产构建通过，浏览器无错误；支付专项 37 项包含在后端集合内，不相加。会员在 390、768、1440px 及浅 / 深色检查，手机付款页无横向溢出；验证三币种报价、缺配置禁用结账和管理员隔离。详见 [验收记录](validation-2026-11-10-membership-billing-v2.md)。

迁移基线独立 PostgreSQL 回归 355 项通过；本次新增 S3 回归和 public 模式存储约束检查，最新结果见迁移复核。旧阶段 294 / 317 / 338 / 348 的结果保留，不累计相加。未验证真实 SMTP、实际渠道付款 / 退款、Apple Pay 设备、云端压力或新模型质量。

本次最终结果：隔离 PostgreSQL **358 passed**；SQLite **351 passed / 7 skipped**，跳过的是需要 PostgreSQL 的检查，已在前一组执行。前端 **14 passed**、构建通过。下面默认命令运行 SQLite；完整云端路径需先在进程环境配置 `TEST_DATABASE_URL`，仅允许 loopback 主机且数据库名以 `_test` 结尾，绝不能设成生产连接串。

```powershell
node --test tests/*.test.mjs
.venv\Scripts\python.exe -m pytest server/tests -q --tb=short --basetemp=output/pytest-handoff-UNIQUE
npm run build
git diff --check
```

`UNIQUE` 换成新的专用目录；pytest 会清理该目录，绝不能指向数据库、历史截图或其他有用输出。

## 8. 接下来做什么

1. 股票搜索 / 财报修复已上线，验收见 [上线记录](validation-2026-11-10-s3-release.md)；后续发布仍须核对部署 SHA 并实际验证研究接口，不能只看 health。
2. 重查测试配置；齐全后实际沙盒付款、回调 / 核对、续费失败 / 成功、取消、退款和重复通知，逐笔对账。
3. 配置缺失时继续无外部账户依赖的 P0：缺渠道编号恢复、拒付、AI pending 恢复、token / 成本统计与费用保护。
4. 完成商业授权、生产邮件、备份恢复、完整研究保存和正式课程；市场情绪未接供应商前关闭能力与扣费。
5. 正式上线另行验收和授权，当前只测试支付、不做 ToB。

可贴到新窗口：

> 请先阅读 docs/README.md、docs/HANDOFF-2026-11-10-TOC-BILLING.md、docs/toc-launch-p0.md 和 docs/test-payments.md。检查并保留 D:\tradingknowledge 的所有未提交改动；数据库迁移已完成，财报 S3 修复已上线，先读迁移复核及上线记录，再核对最新提交；避免回退修复或重新导入非空云端库。继续霁明 ToC P0，仅测试支付、不正式收款、不做 ToB。配置只报告缺项，不输出密钥；齐全后实际沙盒联调，缺失继续无账户依赖任务。前端 5173、后端 8001，启动前检查已有服务。
