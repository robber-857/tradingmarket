# 霁明 Clarora 文档目录

更新：2026-11-10。产品状态以总 PRD 为入口，开发接续以交接文档为入口；验证记录保留当时结果，不覆盖历史测试数字。

当前范围为 ToC P0 与测试支付。正式收款关闭，真实沙盒交易未完成。迁移已提交并完成公开内测部署；线上邮箱登录、支付和自动 AI 简报关闭。独立复核发现的股票搜索 / 财报 S3 字节读取缺口已修复上线并实测恢复；详见 [迁移复核](validation-2026-11-10-migration-audit.md)。

## 从哪里开始

| 目的 | 先读 | 内容与维护边界 |
| --- | --- | --- |
| 了解产品与范围 | [总 PRD](master-prd.md) | 全模块状态、页面流程、会员与深度分析、优先级 |
| 继续开发 / 换聊天 | [开发交接](HANDOFF-2026-11-10-TOC-BILLING.md) | 当前进度、未完成事项、并行修改、端口、配置与接续步骤 |
| 推进 ToC 上线 | [P0 任务表](toc-launch-p0.md) | 任务 ID、阻塞项、固定价格、额度与周期；套餐规则的详细入口 |
| 配置支付与退款 | [测试支付](test-payments.md) | Stripe 银行卡 / Apple Pay / 支付宝、PayPal Sandbox、回调和退款边界 |
| 手动开通会员 | [账号后台](admin-accounts.md) | 账号管理员、权限分配、有效期、撤销与审计；与退款权限分开 |
| 安装与启动 | [项目 README](../README.md) | 依赖、5173 / 8001、本机运行与配置安全 |

## 研究模块与方法

| 主题 | 文档 |
| --- | --- |
| 产品背景、长期方向 | [范围与背景](product-scope.md)；规划实体不等于已交付 API |
| 财报、估值与研究流程 | [研究 PRD](research-prd.md) · [计算方法](financial-methodology.md) · [研究 UI 流程](research-ui-flow.md) |
| 股票识别、报价与 Beta | [股票目录](stock-discovery.md) · [行情数据](market-data.md) |
| 首页与自选参考行情 | [行情口径](dashboard-markets.md) |
| AI 模型、证据与会话 | [AI 配置与实现](ai-research.md) |
| 宏观和机构预测 | [宏观来源](macro-data.md) · [公开预测](public-forecasts.md) |
| 名人与机构披露 | [大资金动向](capital-tracking.md) · 13F、个人报告、来源和更新机制 |
| 新闻、每日简报与期权 | [市场新闻](market-news.md) · [每日简报与期权](daily-brief-options.md) · [真实期权策略](live-option-strategies.md) |

## 部署与迁移

- [Vercel / Supabase 部署与 AWS 迁移边界](vercel-supabase-deployment.md)：资源、环境变量、数据导入、cron、备份和回退。
- [数据迁移独立复核](validation-2026-11-10-migration-audit.md)：数据库逐行比较、S3 内容比对、权限 / 线上接口检查，以及财报兼容修复的发布状态。

## 验证记录

最新：[S3 修复上线验收](validation-2026-11-10-s3-release.md)，股票搜索与两家公司八季财报均返回 200；支付和自动 AI 简报保持关闭。

迁移后最新检查见上方独立复核；以下保留历史验收。会员 / 支付阶段：[2026-11-10 会员与支付 v2](validation-2026-11-10-membership-billing-v2.md)，记录 348 项后端、14 项前端及构建 / 浏览器检查。它覆盖当时本地代码和模拟渠道，不覆盖随后并行修改的数据库 / 部署代码，也不代表真实支付成功。

- 2026-11-10：[首页](validation-2026-11-10-homepage.md)、[简报与期权](validation-2026-11-10-daily-options.md)、[真实策略](validation-2026-11-10-live-strategies.md)、[响应式](responsive-validation-2026-11-10.md)。
- 2026-11-09：[AI](validation-2026-11-09-ai.md)、[宏观](validation-2026-11-09-macro.md)、[行情](validation-2026-11-09-market.md)、[新闻](validation-2026-11-09-news.md)、[股票搜索](validation-2026-11-09-stock-search.md)。

各次测试集合有重叠，不累计相加。截图、运行日志位于忽略的 `output/`，不会随 Git 克隆。

## 更新规则

1. 改产品行为：同步总 PRD 的状态表和对应模块说明；价格 / 额度改动先核对服务端目录。
2. 改上线条件：更新 P0 与配置说明；只记录变量名称、是否配置及核验结果，不记录密钥或一次性登录地址。
3. 完成验证：新建有日期的记录，写明范围、命令、结果与未验证项，不改写旧记录。
4. 换聊天 / 提交代码：更新交接当前状态，先检查 Git 与并行编辑；不清理其他聊天的改动。
5. 数据库迁移与聊天迁移分别描述：交接文件用于开发接续；SQL 文件存在不等于已执行。远程迁移须记录目标环境、迁移版本、备份 / 回滚和验证证据。
