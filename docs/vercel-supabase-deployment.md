# Clarora 内测部署与 AWS 迁移边界

更新：2026-11-10，Australia/Sydney。

## 当前资源

- Vercel：`eltons-projects-1c805292/clarora-market-research`。
- 用户最终选择固定公开地址 `https://clarora-market-research.vercel.app`，不是受保护 Preview。
- Supabase：`bemxbmbtvttirklkpmjx`，trading，Sydney `ap-southeast-2`，Free。
- 数据库：标准 PostgreSQL，独立 `clarora` schema，共 19 张业务表；不向浏览器开放 Data API。
- 文件：私有 `clarora-private` bucket，通过标准 S3 接口访问。
- 服务端配置在 `.env.supabase.local`，已被 Git 和 Vercel 上传排除。不得提交或输出内容。
- 本地 `.env` 未切换为云端配置；本地 SQLite 与云端数据库不会自动双向同步。

## 已执行的迁移

先通过 SQLite backup API 创建一致性备份，再在 PostgreSQL 单个事务中导入并核对行数。
备份位于 `output/pre-supabase-20261110-180524/`，原始 SQLite 保留。

导入：users 2，sessions 1，throttle 12，editions 1；其余会员、支付、退款、研究保存表为空。
675 个 JSON 快照（约 42 MB）已上传到私有存储并逐个回读比较；不上传 `.env`、SQLite 或任意目录文件。
缓存按来源重建；未将本地 SEC 大体积缓存全部上传。

## 内测开关

- `CLARORA_MODE=public`，禁用公网开发登录链接。
- `EMAIL_LOGIN_ENABLED=0`：没有自有发件域名，邮件登录尚未开放，界面禁用邮箱提交。
- `BILLING_TEST_ENABLED=0`：测试支付代码保留，渠道凭据未配置，不接受正式收款。
- `DAILY_BRIEF_ENABLED=0`：保留迁入的简报，不自动产生 AI 费用。
- Vercel 进程内后台循环关闭，改用独立、带 Bearer 密钥的有限时长 cron API。
- 以上是内测运营状态，不应描述为真实支付、邮件或所有数据源已通过线上验收。

## 配置与重新部署

1. 修改本机私密配置。密码用英文引号包围，连接串需要 URL 编码；不把密钥写入命令行。
2. `python -m scripts.configure_vercel` 将允许列表中的配置通过 stdin 上传到已关联项目的 Production 环境。
3. 使用 Vercel CLI 部署。变更环境变量后需要重新部署才能生效。
4. Preview 应使用单独数据库、bucket、域名和密钥，不复用生产支付回调。

迁移文件：`supabase/migrations/202611100001_clarora.sql`。
数据库导入：`python -m scripts.migrate_database --sqlite <备份路径> --briefs <备份路径>`。
目标表必须为空，脚本拒绝合并或覆盖非空目标；重新迁移前先设计增量同步，不能直接重复导入。
文件导入：`python -m scripts.migrate_objects` 默认只报告，`--apply` 上传并核对，已有内容不同则停止。

## Resend 待办

拥有域名后，在 Resend 添加例如 `auth.example.com`，按其提供的值配置 DNS 并等待验证。
填写 Resend SMTP 的 host/port/user/password/from；先完成真实邮件收取及一次性登录验收，再设置 `EMAIL_LOGIN_ENABLED=1` 并重新部署。
当前不会用 Resend 测试发件地址冒充可向所有内测用户发信的正式发件配置。

## 调度

`deploy/supabase-cron.sql` 使用 pg_cron、pg_net 及 Vault 的 `clarora_base_url`、`clarora_cron_secret`。
新闻每 30 分钟，预测每小时，简报每小时检查悉尼当地时间与数据库状态；简报开关为 0 时不生成。
调度需在上线 URL 可用后配置，并验证 HTTP 响应；SQL job 成功提交不等于远程任务执行成功。
跨实例租约防重入，支付/用量采用短事务的 PostgreSQL advisory lock 保留串行核对语义。
锁设计适合当前小规模内测；扩大规模前应改为按账户/资源锁，并进行负载验证。

## 备份与回滚

Free 方案不依赖付费自动备份：定期用 `pg_dump` 备份 clarora schema，同时备份私有对象和迁移版本。
Vercel 回滚仅回滚代码，不回滚 PostgreSQL 或对象存储；有云端新写入后不能直接切回旧 SQLite。
历史会话可自然过期；AI 会话历史保留一小时，未完成的额度预留需要核对，不自动认定失败退款。

## 以后迁 AWS

- PostgreSQL 用 dump/restore 迁到 RDS，修改 `DATABASE_URL`，生产使用 TLS，验证事务/权限/索引。
- S3 对象保留路径，复制到 AWS bucket，移除 `S3_ENDPOINT_URL`、更新区域和 bucket。
- ECS/Fargate 使用任务角色取代静态 AWS 密钥，现有 boto3 默认凭据链支持。
- Python API 保留 FastAPI；定时任务改由 EventBridge 调用相同鉴权接口或任务入口。
- 业务数据不依赖 Supabase Auth、PostgREST 或专用数据库函数；Supabase 专有 cron/storage 配置与业务 schema 分离。

## 验证记录

- 隔离 PostgreSQL 全量后端回归：355 项通过（2026-11-10 最终发布前重跑）。
- 前端数据测试：14 项通过；生产构建通过。
- 邮件关闭状态改动后，数据库/会员相关回归：18 项通过。
- 真实 Supabase S3 写入、读取、元数据和删除探针通过；675 个迁移对象逐个回读验证。
- 本机加载生产入口、连接真实 Supabase：health/account/plans/briefs/billing-status 均返回 200，公网模式无开发登录链接，邮件关闭返回 503。
- 上述入口检查在本机执行；Vercel 远端构建和浏览器验收需以实际部署结果为准。
- Vercel 构建器拒绝根 requirements 的嵌套引用后，已改为平铺生产依赖清单，并排除 pytest 等测试依赖。

## 已发布结果

- Production：`https://clarora-market-research.vercel.app`。
- 部署 ID：`dpl_5Ae3sqQE88fraLTBJezx7i3iUR12`，Vercel 状态 READY，固定域名已绑定。
- 浏览器实际打开固定地址成功，无 Vercel 登录拦截；`/api/health` 返回 status=ok。
- 浏览器会员页加载数据库支持的方案并显示“邮箱登录暂未开放”“仅测试 · 正式收款未开放”。
- 浏览器成功读取 2026-11-10 已迁移简报的完整内容。
- Supabase pg_cron/pg_net 已启用，3 个 Clarora job 已注册且 active；Vault 保存 URL 与鉴权密钥，cron 命令不嵌入明文密钥。
- 2026-11-10 18:28 / 18:29 悉尼时间，通过临时 pg_cron 验证任务沿相同 Vault → pg_net → Vercel 链路触发三个接口，均 HTTP 200、status=ok，无超时；临时任务已删除。18:30 正常 clarora-news 调度再次成功，远端 HTTP 200。简报和预测的原定时周期尚未到达，但相同接口及真实调度链路已验证。
- `DAILY_BRIEF_ENABLED=0` 使简报任务不执行 AI 生成；成功响应代表调度与接口正常，不代表所有第三方新闻源可用或有新预测需要更新。
- 首次发布来自本机工作区。本次将迁移、持久化、会员/测试支付依赖、UI 和部署配置一并纳入 GitHub main；后续发布以该分支为准，不要从迁移前提交重新部署。Git 推送后应核对 Vercel 部署的 gitSource.sha 与 origin/main 一致且状态 READY。
