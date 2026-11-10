# 动态股票研究验收 · 2026-11-09

- 获取 SEC 官方目录：10,419 条证券记录，字段 CIK、名称、代码、交易所；此数量不表示已完成 10,419 只股票估值。
- 搜索验证：`tesla` → TSLA、`AMZN` 精确优先、`BRK.B` → BRK-B；未知代码为空候选并返回明确 404。
- 真实财报：AMD、TSLA、AMZN、META、GOOGL 返回 200。自动保留 CIK、正式报告期与证据源。
- 真实行情：AMD、TSLA、AMZN、GOOGL 报价及 Beta 返回 200。AMD、AMZN 的 DCF 可计算；GOOGL 自动倍数按多证券限制留空。
- AMD 真实 OpenAI 财报解读和连续追问均 200；TSLA 不带 DCF 假设的基本面解读 200；浏览器 AMD 基本面解读完成，引用包括财报指标和条件终值权重。
- TSM 外国申报 422、SPY 基金/无 Company Facts 422；JPM 当前收入标签未映射，提示金融专用模型。没有替代演示财报或自动编造输入。
- 浏览器检查：动态候选、上下键与 Enter、全局搜索 AMZN、关注 AMD 后从清单跳回、未知代码错误、GOOGL 暂停每股估值、TSM 申报格式提示。
- 桌面 1440×1080 与手机 390×844 无横向溢出；长英文公司名正常换行。测试添加的 AMD 关注与无效代码最近记录已清理。
- `npm run test:finance`：126 passed，只有既有 Starlette/httpx 弃用提示。沙箱运行设置项目内 `PYTEST_DEBUG_TEMPROOT`。
- `npm run build`：通过。生产 JS 约 362.68 kB / gzip 115.44 kB。

证据位于 `output/research-*.json`、`output/expanded-market-*.json`、`output/expanded-ai-*.json` 和 `output/playwright/expanded-ai-result.yml`、`stock-search-mobile.png`、`expanded-stock-desktop.png`。

当前没有额外数据源密钥要求，也未部署公网。覆盖依据为动态证券目录和数据能力检查，不是为每一家发行人手工核验过的会计适配清单。特殊申报、非美元、自定义标签、金融行业、多上市证券及不完整财务输入仍有明确限制。
