# 数据迁移独立复核与财报存储修复

日期：2026-11-10，Australia/Sydney。复核基线为 `69fc9e6`（PostgreSQL / S3 迁移及部署）。本次从干净工作区开始；不重新导入数据、不修改云端表或对象、不启用邮件、支付或自动 AI 简报。

## 结论与发布状态

数据库导入未发现数据丢失：备份中的 16 张会员业务表及 1 张简报表，与云端逐行一致。发现一个确实影响线上功能的 S3 兼容缺陷：`ObjectPath` 未实现 SEC 使用的 `read_bytes()`，股票搜索和财报接口返回 HTTP 500。

本地已补齐原始字节读取，`read_text()` 复用该方法；补充回归并完成验证。另修正四项 public 模式测试未声明 PostgreSQL 依赖的问题，不放松运行时的数据库安全要求。**本次未部署修复；线上仍须发布该修复并复验股票搜索 / 财报。** 健康接口 200 不代表所有研究功能可用，也不能仅凭全量 PostgreSQL 测试通过宣布迁移无问题。

## 数据库与权限核对

- 源：`output/pre-supabase-20261110-180524/` 中的两个 SQLite 一致性备份，以只读方式打开，`PRAGMA integrity_check` 通过。
- 目标：Supabase `clarora` schema，19 张表；核对事务使用 PostgreSQL `REPEATABLE READ READ ONLY`。
- 2 个用户、1 个会话、12 条限流记录和 1 条每日简报的全部字段一致。其余迁入会员 / 付款 / 退款 / 保存 / 审计表在源端与目标端均为空；不能据此声称迁过真实支付流水。
- 共享 AI 会话与任务租约为新增运行时表，没有对应 SQLite 导入内容。
- 未发现未验证约束；`anon` 与 `authenticated` 角色均无业务 schema 的 USAGE 权限；私有存储 bucket 的 public 标记为 false。
- 最初文本读取出现微秒级时间戳差异。云端 `extra_float_digits=0` 会舍入 double precision 的文本返回；使用 psycopg 二进制游标后逐行完全一致。没有为此修改客户记录或时间戳。

## 文件核对及迁移后的变化

本地扫描 678 个符合迁移白名单的 JSON 文件；并发读取云端并比较内容 SHA-256：

| 结果 | 数量 | 解释 |
| --- | ---: | --- |
| 内容一致 | 674 | 逐个读取比较通过 |
| 内容不同 | 1 | `news_editions/2026-11-10.json`，当天新闻归档在两端继续更新；不是不可变证据快照 |
| 本地有、云端无 | 3 | 2 个 reports、1 个 news_snapshots；文件修改时间晚于源备份，属于迁移后本地新增文件 |
| 读取错误 | 0 | 无对象读取失败 |

此前迁移报告为 675 个对象，当前本地为 678；本地和云端没有双向同步。这里核对的是当前文件与云端，未保留的原始迁移清单无法据此重建；不覆盖较新的云端新闻归档，也不自动上传迁移后本地测试产物。后续迁移建议保存键、哈希和版本清单到私有备份，便于区分原始迁入内容与后续变化。

## 线上接口与调度

只请求公开读取接口和无鉴权的保护检查，未触发任何已授权 cron、支付或模型生成。

| 接口 / 检查 | 结果 |
| --- | --- |
| health、匿名 account、会员方案、billing status | HTTP 200 |
| 简报目录、2026-11-10 完整简报 | HTTP 200 |
| 未登录访问账号后台、支付检查 | HTTP 401 |
| 缺少 Bearer 的 cron/brief | HTTP 401 |
| `/api/research/assets?query=AAPL` | HTTP 500，受缺失 read_bytes 影响 |
| `/api/research/AAPL` | HTTP 500，同一存储兼容问题 |

线上返回 `localMode=false`、`emailLoginEnabled=false`、`salesEnabled=false`；测试支付 `enabled=false`，Stripe / PayPal 均未启用。三个 cron job 均 active；复核窗口中正常新闻调度有一次 succeeded，pg_net 最近记录七次 HTTP 200、无超时。pg_net 汇总并非每条计划任务的完整来源归因，不冒充三个任务都已跑过正常周期，也不表示所有第三方数据源成功。

## 修复与测试

修复：`server/object_store.py` 实现 `read_bytes()`，直接返回 S3 body 的原始字节；`read_text()` 再按指定编码解码，保留不存在对象映射为 `FileNotFoundError` 的行为。未变更数据库 schema、对象键、付款规则或任何运营开关。

新增 `server/tests/test_object_store.py` 使用内存 S3 客户端，但走真实 `ObjectPath`、SEC 股票目录和财报读取路径，验证原始字节 / 哈希、UTF-8、缺失文件和有效缓存不请求外部 SEC。修复前两项测试均复现 AttributeError，修复后两项通过。旧 PostgreSQL 回归多使用本地文件缓存，因此没有覆盖这个 S3 适配缺口。

- 迁移基线 PostgreSQL 全量回归：355 passed。
- 最终独立 PostgreSQL 全量回归：358 passed、无跳过；复用本项目本地容器，新建独立 `clarora_audit_20261110_test` 库，未在生产数据库执行测试或 TRUNCATE。
- 最终本地 SQLite 回归：351 passed、7 skipped。3 项云端专属测试和 4 项 public 数据库测试明确要求隔离 PostgreSQL；同一组在上述 PostgreSQL 回归中全部执行。首次 SQLite 回归暴露四项测试环境依赖未声明，已修正；新增测试确认 public 无 DATABASE_URL 时拒绝回退 SQLite，没有为过测放宽生产约束。
- 前端 Node 测试：14 passed；`npm run build` 成功。
- 一条既有 Starlette/httpx 弃用提示，不影响本次测试结果。
- 真实沙盒付款 / 退款、SMTP 收件、带真实用户的跨设备登录、模型费用与全量供应商质量仍未验证；本次未重启本地 5173 / 8001 服务。

## 可重复的只读核对

新增 `scripts/audit_migration.py`，从显式指定的私有配置读取凭据，只输出表计数、比对结果、权限和接口状态；不打印记录、密钥、会话 token、对象正文或渠道错误详情。

```powershell
.venv\Scripts\python.exe -m scripts.audit_migration --env-file .env.supabase.local --backup output/pre-supabase-20261110-180524 --report output/migration-audit-20261110-final.json
```

报告和本地测试日志存放于忽略的 `output/`；不提交私有备份或原始数据。本报告只记录本次观察，不保证此后数据或线上代码状态不再变化。
