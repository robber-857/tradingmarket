# 宏观日历验证记录

日期：2026-11-09。本地验证，未部署公网。

## 已通过

- 财报、估值、行情、AI 与宏观测试合计 **160 项通过**。保留一项原有 Starlette/httpx 弃用提示。
- `npm run build` 成功。
- `/api/macro/calendar` 实际返回 HTTP 200，默认窗口取得 17 项指标/发布事件，覆盖 CPI、非农、PCE、FOMC。
- BLS 公共 API 真实连接成功；当前取得 CPI / 核心 CPI 季调环比和未季调同比，以及非农相邻月增量。
- 美国劳工部原始 PDF 真实读取成功。已从原文核验本期和下期 CPI / 非农的日期、时间、统计所属月。
- BEA 官方排期、PCE 新闻稿及月度物价表真实读取成功。
- 美联储日历与当前/前次声明真实读取成功，解析完整目标区间。
- OpenAI 实际 API：PCE 解读和同一会话追问均 HTTP 200；回答引用前值与实际值，并承认没有一致预期、不能断言比特币必然下跌。
- 浏览器实际操作：CPI 解读和文本框追问成功，数字引用指向官方序列；刷新日历后当前解读和追问记录仍保留。
- 浏览器检查：PCE 类型筛选；美东到北京、悉尼的时区转换；1440 × 1080 桌面双栏；390 × 844 手机列表、三值显示、事件详情跳转。

## 当前限制

- Trading Economics 可选凭据未配置，供应商适配器仅完成合成响应单元测试，未宣称账户联调成功。
- 一致预期缺失，页面明确留空，不能判断超预期。
- BLS 网站直接日历请求 HTTP 403；通过劳工部转载原文补充最近与下一次日期。更远排期不按惯例生成。
- 免费数据按来源缓存十五分钟或一小时，不保证秒级发布响应。
- BLS 是当前修订版本计算结果，不是首发历史值。免费来源仅抓最新报告及可取得排期，不是完整历史回放系统。
- FOMC 未来会议只有日期证据时，不推算具体发布时刻；已公布声明的准确时刻独立提取。
- PCE 本轮覆盖总量/核心环比；跨资产行情窗口、会议发言、点阵图和完整 PCE 分项没有接入。

## 本地证据

- `output/macro-live.json`
- `output/macro-ai-live.json`
- `output/macro-ai-followup.json`
- `output/playwright/macro-desktop-wide.png`
- `output/playwright/macro-mobile.png`
- `output/playwright/macro-mobile-detail.png`
- `output/playwright/macro-followup-final.yml`
- `output/playwright/macro-refresh-pinned.yml`

测试与抓取输出不包含 API Key。合成测试数据仅存在测试夹具，不作为产品数据降级源。
