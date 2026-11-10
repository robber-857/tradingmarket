# 行情接入本机验收 · 2026-11-09

## 已执行

- 用户在本机配置 Twelve Data Key 后，真实读取 AAPL、INTC、NVDA、MSFT 报价与历史日线，四只股票均返回可用数据。
- 样本报价时点为 2026-11-06 15:59 ET，核验时为下一交易日盘前，UI 显示最近可得报价/休市及实际时间。
- AAPL 报价 342.37，P/E 37.64、P/B 44.39、P/S 10.39，Beta 1.039177。
- INTC 报价 56.28，TTM 净利润非正，因此 P/E 不适用；P/B 2.60、P/S 4.99，Beta 2.045（界面舍入）。
- NVDA 报价 186.64，P/E 23.32、P/B 19.64、P/S 14.85，Beta 1.852522；MSFT 报价约 530.61，倍数 27.63 / 8.38 / 11.38，Beta 0.944061。
- Beta 样本为 2024-11-11 至 2026-11-06，499 个配对收盘价、498 个日收益率。用 NVDA、MSFT 导出中的股票/SPY 价格重新计算，和服务器 Beta 在浮点容差内一致。
- 真实 OpenAI API：AAPL 倍数解读及连续 Beta 追问均 200；浏览器完成 NVDA「解读市场敏感度 → 发送 → 引用弹层 → 导出」全流程。引用 Beta 显示 1.853，无美元或倍数单位误标，来源链接为 Twelve Data 时间序列说明。
- 桌面 1440×1080、手机 390×844 无页面横向溢出。检查历史曲线区间及日期滑块；CAPM 自动带入 Intel Beta 2.045 和估算股权市值 298.8468 十亿美元。
- 旧报告期禁用行情刷新和当前倍数联动；切回最新报告恢复。更换股票不保留前一股票行情；刷新行情清除旧 AI 会话。
- `npm run build` 成功。`npm run test:finance` 103 项通过；沙箱测试设置 `PYTEST_DEBUG_TEMPROOT=D:\tradingknowledge\output\pip-tmp` 以避开系统临时目录权限问题。仅有既存 Starlette/httpx 弃用警告。
- 检查构建产物、行情快照及 AI 导出，未发现本机 OpenAI/Twelve Data Key 字符串。
- 本地 API 重启至最新代码，前端预览健康检查 200。已启动默认浏览器打开更新后的本地入口；Codex 内嵌打开请求排队且一次 CUA 打开超时，浏览器自动化的页面加载与截图独立通过。

## 证据

- `output/market-live-aapl.json`、`output/market-live-nvda.json`、`output/market-live-msft.json`
- `output/market-ai-first.json`、`output/market-ai-followup.json`
- `output/playwright/market-ai-browser-export.json`
- `output/playwright/market-final-desktop.png`、`output/playwright/market-mobile.png`
- `output/playwright/market-history-period.yml`、`output/playwright/market-ai-browser.yml`

## 边界

这里只验证本地数据链路、确定性计算与用户交互，不代表全天候供应商质量、完整合并行情或 SaaS 再分发授权已完成。行情是页面加载/手动刷新快照；倍数使用已披露股数估算市值，未覆盖之后的回购增发。默认实时源来自部分交易场所，Beta 使用不含分红再投资的拆股复权价格。AI 引用与数字校验不保证每一句推论都充分。其他宏观/新闻/社交情绪看板仍是演示。
