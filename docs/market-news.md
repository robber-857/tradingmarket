# 市场热点：来源、方法与每日更新

本地入口：`http://127.0.0.1:5173/#news`。新闻、社区观点和模型推论分别标注。当前实现采集公开摘要，不绕过登录、不采集浏览器凭据，也不声称已读取新闻全文。

## 数据覆盖

| 来源 | 内容 | 默认凭据 | 范围与限制 |
| --- | --- | --- | --- |
| CNBC | 美股、公司与宏观新闻 | 无 | RSS 中按金融关键词筛选；不是全部财经新闻 |
| CoinDesk / Cointelegraph | 加密市场、行业与监管 | 无 | 发布方标题与短摘要，不复制全文 |
| Federal Reserve / SEC | 政策与机构公告 | 无 | 新闻发布时间不等于经济指标发布时间；经济日历仍走独立模块 |
| Reddit | stocks、investing、wallstreetbets、CryptoCurrency、Bitcoin | 无 | 每社区 Top(day) RSS 最多 25 条，按发布时间再筛最近 24 小时；保留社区排名，不跨社区合成“全站热度” |
| X | 固定金融关键词最近英文讨论 | 可选 `X_BEARER_TOKEN` | 官方 recent search 最多 100 条样本，无全量翻页；样本内互动排序，不是官方趋势榜 |

RSS 不提供 Reddit 点赞与评论数，所以不填虚构数字。来源限流或失败会显示状态；最多使用一天内的缓存并标记“更新失败”。新闻合并只按去除追踪参数后的相同 URL 去重，不把相似标题误当成同一事实。

X 固定查询覆盖 SPY、QQQ、NVDA、BTC、ETH、Bitcoin、FOMC、US inflation，英文且排除转帖。排序公式为点赞 + 2×转发 + 2×引用 + 3×回复，只比较已取得的样本；缺少所需指标的帖子跳过，不把缺失当零。未配置时不发请求、无模拟榜单。本机尚未配置 X，适配器经过合成数据测试，未完成真实账户联调。

官方说明：[X recent search](https://docs.x.com/x-api/posts/search-recent-posts)、[X 定价](https://docs.x.com/x-api/getting-started/pricing)、[美联储 RSS](https://www.federalreserve.gov/feeds/feeds.htm)、[SEC RSS](https://www.sec.gov/about/rss-feeds)。公开可读取不代表任何规模的商业再分发均获授权，付费客户展示前需核对各来源条款。

## 更新与保存

- FastAPI 启动后立即采集，此后每 30 分钟执行；前端可见时每分钟检查服务端，手动刷新同样遵守缓存与限流。
- 新闻 RSS 成功缓存 30 分钟，Reddit 串行且间隔至少两秒；失败使用持久化退避及 Retry-After。X 成功缓存一小时。
- 按悉尼日期保存每日目录，保留最近 30 天。目录是该日最后更新时的滚动 24 小时发布方新闻，**不是完整自然日新闻，也不是自动生成的 AI 日报**。
- 原始发布时间按 UTC 保存，显示时遵循用户时区。每日目录分日规则固定为悉尼，界面有说明。
- 服务离线期间不会继续采集或补造归档。部署为常驻服务后才能无人值守运行；此版本没有邮件、微信或其他推送。
- 社交帖子不写入长期每日目录；分析快照保存两天，可发起 AI 分析的快照最长一天。源缓存用于近期读取，未建立永久社交档案。
- `NEWS_BACKGROUND_ENABLED=0` 进程环境变量可关闭后台轮询，测试自动关闭。手动请求接口仍可采集。

## AI 与跳转

进入市场热点 → 选择市场新闻 / Reddit / X → 筛选主题、时间或关键词 → 选择单条 AI 解读 → 生成 → 阅读结论、可能影响及下一步验证 → 点击来源核对 → 继续追问。

市场新闻默认右栏提供“生成今日重点”，从最近 24 小时按美股、Crypto、宏观类别选择最多六条可用新闻。选择依赖时间与类别，不是市场重要性评分，也不保证当天每类都有新消息。选择一条消息会切换到该条独立上下文；手机上自动滚动到解读区。历史目录保留原文访问，返回实时视图后才能生成新解读。

AI 仅收到标题、有限预览、来源类型、发布时间、采集时间及缓存状态；优先一句结论和两三条影响。每条结论绑定服务端来源 ID，数字需使用证据账本占位符并引用对应文章，链接由服务端提供。来源陈述、市场推论、条件情景分开显示。没有行情事件窗口或市场预期数据时，不证明新闻导致涨跌、不判断超预期、不承诺方向或收益。

会话绑定文章和快照，后台刷新不替换正在分析的证据；最多八轮，一小时到期。OpenAI 使用现有 `.env` 配置，只有点击生成或发送追问才调用，仍按模型用量收费。格式与来源检查不能保证模型所有推论正确，应以原文和后续数据复核。

## 配置与接口

免费新闻无需新增 Key。可选 X 配置仅后端读取，不使用 VITE 前缀：

```dotenv
X_BEARER_TOKEN=
```

接口：`GET /api/news/feed`、`GET /api/news/editions`、`GET /api/news/editions?day=YYYY-MM-DD`、`POST /api/news/explain`。AI 请求字段为 snapshot_id、可选 article_id、question 和 conversation_id。缓存位于 `server/cache/news/`，分析快照位于 `server/news_snapshots/`，每日目录位于 `server/news_editions/`；均不提交版本控制。

## 开源技能选择

| 工具 | 适合用途 | 本次结论 |
| --- | --- | --- |
| [AIHOT Skill](https://github.com/KKKKhazix/khazix-skills/blob/main/aihot/SKILL.md) | AI 行业最近动态、热点、日报和搜索 | 新版服务 `https://aihot.news`，公开 GET 无 Key。已试读 latest 接口，但内容侧重 AI，不能替代金融新闻或 Reddit / X 榜单 |
| [last30days](https://github.com/mvanhorn/last30days-skill) | 对金融主题做跨平台近期研究，可涉及 Reddit、X、StockTwits 等 | 适合研究员专题采集；不同来源依赖相应工具、凭据与权限，不等于永久免费全网数据。已阅读，未安装或执行 |
| [last24hours](https://github.com/jask04/last24hours-skill) | 最近一天的跨平台研究与市场主题工作流 | 可参考时间窗口和出处整理方法；外部采集依赖需另配。已阅读，未安装或执行 |

AIHOT 正式技能：[SKILL.md](https://github.com/KKKKhazix/khazix-skills/blob/main/aihot/SKILL.md)。本次按 v2.0.0 请求 `/api/v1/agent/latest`，服务返回成功；未作为产品新闻源集成。技能代码的 MIT 许可不等同服务内容商用许可；[AIHOT 服务条款](https://aihot.news/terms) 对外商业用途要求书面授权。付费 SaaS 不能仅凭技能开源就默认直接转售其聚合内容。

当前产品采用自己可测试的 RSS 采集服务；这些技能可作为研究员的辅助工作流，不替代来源管理、定时任务与后端证据校验。

2026-11-10 扩展：新增独立“每日市场简报”页面，按日自动调用 OpenAI 并保存历史。本文的“AI 仅点击时生成”指市场热点页面的按需解读；定时 AI 简报的配置、费用与去重机制见 [每日简报与期权说明](daily-brief-options.md)。
