# ToC 会员页与支付运营补充验收

日期：2026-11-10（Australia/Sydney）。本轮保留既有未提交改动；仅测试支付，不做 ToB，不开启正式收款。

记录范围：以下为会员页与支付运营完成时的历史验收，早于同日另一聊天开展的 PostgreSQL / 对象存储 / 部署迁移。本次文档整理保留原结果，没有把这些测试重新归因给仍在修改的代码；当前状态见 [交接](HANDOFF-2026-11-10-TOC-BILLING.md)。

## 运行与测试配置

开始时前端 5173、后端 8001 均返回 HTTP 200，复用现有服务。后端改动完成后核对监听进程及命令行，仅重启本项目 8001 后端，未重复启动前端或另占端口。

本轮重新读取服务端配置，仅输出状态，不输出配置值：

| 配置 | 本轮检查状态 |
| --- | --- |
| BILLING_TEST_ENABLED | 未启用 |
| STRIPE_TEST_SECRET_KEY | 缺失 |
| STRIPE_TEST_WEBHOOK_SECRET | 缺失 |
| STRIPE_TEST_PORTAL_CONFIGURATION | 缺失 |
| PAYPAL_SANDBOX_CLIENT_ID | 缺失 |
| PAYPAL_SANDBOX_CLIENT_SECRET | 缺失 |
| PAYPAL_SANDBOX_WEBHOOK_ID | 缺失 |
| BILLING_ADMIN_USER_IDS | 缺失；与账号管理员配置分开 |

因此没有执行实际 Stripe、支付宝或 PayPal Sandbox 付款、续费、退款。商户授权、支付钱包设备、回调投递仍未验证。配置方法见 [测试支付](test-payments.md)。

## 界面改动

参照用户提供的 [Dribbble 会员卡设计](https://dribbble.com/shots/27870815-SaaS-Pricing-Page-UI-UX-AI-Voice-to-Text-Platform)，采用外层中性底、内层价格与 CTA 的结构；浅色白灰与深色炭灰分别定义颜色、边界与按钮对比。

- 账户登录 / 额度缩成紧凑区域；「会员方案」「付款与账单」「研究记录」通过页内导航切换。
- 三张主卡展示研究、高级、专家会员；免费体验与七天通行证保留在辅助区。
- 保留全部现有价格与额度；未接入的市场情绪移至说明，不当作当前可用权益推销。
- 付款页明确展示银行卡（信用卡 / 借记卡）、Apple Pay、支付宝、PayPal；按币种展示有效渠道，提供方案汇总与续费方式。
- 登录后从服务端获取报价；只有报价与当前选择匹配且渠道已配置时才能结账。切换币种不发送中间无效渠道组合；重复订单仍由已有后端约束拦截。
- 七天入口、已登录额度、退出登录、管理员入口、已保存研究和原付款 / 退款功能保留。
- 会员中心、后台按需加载，最终主 JS 约 470 KB，生产构建无超过 500 KB 的单包提示。

## 独立于商户账户完成的 P0 工作

新增 `server/payment_operations.py` 与后台「测试支付检查」：

- `GET /api/admin/billing/readiness`：仅管理员可见的配置存在性 / 格式状态；不会返回密钥值。明确标识配置检查不等于真实凭据、支付宝资格或回调已验证。
- `GET /api/admin/billing/orders`：默认查看超过十五分钟的 creating / pending 订单，分页，可包含最近订单；不返回 Checkout URL。
- `POST /api/admin/billing/orders/{id}/reconcile`：读取渠道真实状态，经已有身份、金额和币种校验同步结果。PayPal 核对明确使用 `capture=False`，不会发起收款；Stripe 仅 GET 查询。
- 每次渠道核对成功或失败均记录操作者、原因、订单、前后状态与时间。不提供手动置 paid，不虚构付款，不自动释放不明订单。
- 渠道编号缺失时提示先核对原创建请求，不强行关闭。没有实现扫描所有异常的后台任务、关联缺失渠道 ID、自动处理拒付或恢复 AI pending 额度；这些继续留在 P0。
- CLI 可执行 `.venv\Scripts\python.exe -X utf8 -m server.payment_operations`，输出同样的无密钥检查结果。

账号管理员或退款管理员可查看并执行只读渠道核对；退款审核仍由原 `BILLING_ADMIN_USER_IDS` 控制，没有扩大退款权限。

## 普通与深度分析的真实区别

本轮检查到模型配置为 `gpt-5.4-mini`；没有因用户提问而修改模型或调用模型生成内容。

- 两者读取相同 `OPENAI_MODEL`，使用同一证据快照、结构和引用校验。
- 普通：默认 reasoning medium；宏观普通模式为 low；max_output_tokens 6000。
- 深度：reasoning high；max_output_tokens 10000；添加反例、敏感性、证据缺口与证伪条件要求。
- 上述是 token 预算上限，不是字数承诺；深度不是更大模型，也不包含额外联网研究。
- 追问是沿用当前会话提出后续问题，按当前选择的普通 / 深度模式扣对应一次额度。

## 验证结果

- 完整 Python 回归：**348 passed**，一条既有 Starlette/httpx 弃用提示。
- 前端 Node 测试：**14 passed**。
- 新增支付运营测试 10 项；与原支付专项合计 **37 passed**，已包含在完整回归中，不重复相加。
- `npm run build` 成功；`git diff --check` 通过。
- 浏览器使用真实本地服务核对 CNY 高级月度 24900 分、CNY 七天 4900 分、AUD 七天 1000 分、AUD 月度 2900 分；验证卡月付自动续费和 PayPal 单次手动续购。没有发起 Checkout 或实际付款。
- 390、768、1440 像素视口，浅色 / 深色套餐页检查；390 像素付款页两主题检查，无页面横向溢出。属于浏览器视口模拟，不是实体手机支付验证。
- 验证后台检查列表、待确认订单空态、刷新；未登录访客被后台拦截，付款页登录 CTA 正确聚焦邮箱输入框；已保存研究入口正常。

截图保存在被 Git 忽略的 `output/playwright/`，主要为 `member-cards-lightness.png`、`member-cards-darkness.png`、`member-mobile-lightness.png`、`member-mobile-darkness.png`、`payment-readiness.png`。没有新增真实用户、付款或赠送权益。

渠道查询接口参考：[Stripe Checkout Session 查询](https://docs.stripe.com/api/checkout/sessions/retrieve)、[PayPal Orders v2](https://developer.paypal.com/docs/api/orders/v2/)。保留现有 Stripe API 固定版本，本轮未升级渠道接口版本。
