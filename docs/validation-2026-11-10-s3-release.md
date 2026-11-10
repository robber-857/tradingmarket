# 财报 S3 修复上线验收

日期：2026-11-10，Australia/Sydney。用户授权提交 GitHub、部署现有生产站点并验证股票搜索与财报，同时保持支付和自动 AI 简报关闭。

## 发布范围

- 修复提交：`fd871e87450b35e6beb157b243197d1d2aa390a8`，已推送 `robber-857/tradingmarket` 的 `main`。
- 包含 S3 `read_bytes()` / `read_text()` 兼容修复、相关回归测试、public 测试数据库依赖说明、只读迁移核对脚本和文档。
- GitHub 推送触发现有 Vercel Production 自动部署，未重复手工部署。
- 修复首次验收部署：`dpl_EqjAKW1Gg7KyMsM5Wu1wzp6GUX2o`，状态 READY；Vercel 部署列表确认来源提交为上述 SHA。
- 固定入口：[Clarora](https://clarora-market-research.vercel.app)。

没有重新执行数据库迁移、导入或环境变量上传；没有删除历史数据或更改支付 / AI 运营开关。以下验证为真实公开域名请求，不使用模拟响应，也未调用模型生成或付款接口。正常研究读取会写入已有的缓存 / 证据快照流程。

## 实际接口验证

| 请求 | 结果 | 业务内容检查 |
| --- | --- | --- |
| `GET /api/research/assets?q=AAPL` | HTTP 200 | 返回 AAPL，SEC 目录 SHA-256 有效 |
| `GET /api/research/assets?q=Microsoft` | HTTP 200 | 返回 MSFT，SEC 目录 SHA-256 有效 |
| `GET /api/research/AAPL` | HTTP 200 | 八个季度、三条来源、非空 snapshotId；来源哈希有效 |
| `GET /api/research/MSFT` | HTTP 200 | 八个季度、三条来源、非空 snapshotId；来源哈希有效 |
| `GET /api/health` | HTTP 200 | status=ok |

首次财报检查 AAPL 约 11.4 秒、MSFT 约 9.0 秒，属于本次观测，不是延迟承诺。原先由 `ObjectPath.read_bytes()` 缺失导致的 HTTP 500 在这些真实调用中消失。没有据此宣称全部发行人和所有外部数据源已通过质量验收。

## 开关与历史内容

部署前、部署后都从线上 API 核对：

- `/api/billing/status`：`enabled=false`、`testMode=true`。
- `/api/membership/plans`：`salesEnabled=false`、`emailLoginEnabled=false`。
- `/api/briefs`：`schedule.enabled=false`；仍有原来的一条历史简报。

因此支付和自动 AI 简报继续关闭，正式收款未开启；没有触发真实沙盒交易、支付退款、邮件或自动模型生成。关闭自动生成不妨碍阅读历史简报。

## 验证依据与后续

修复前已完成：隔离 PostgreSQL 358 passed，SQLite 351 passed / 7 PostgreSQL 专属检查跳过，前端 14 passed、生产构建成功。发布时未更改业务代码，以上结果继续适用；Vercel 远端构建再次成功。

脱敏摘要保存在忽略的 `output/release-before.json`、`output/release-after.json` 及部署元数据文件。本文记录修复首次验收部署；随后同步文档可能产生同业务代码的新部署，应继续核对最终部署 SHA、Ready 状态和线上开关。

下一步仍为 SMTP / 域名、真实测试支付联调、备份恢复演练、监控与成本保护，不包含开启正式收款。迁移数据一致性详情见 [迁移复核](validation-2026-11-10-migration-audit.md)。
