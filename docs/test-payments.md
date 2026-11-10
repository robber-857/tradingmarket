# 霁明测试支付、续费与退款

2026-11-10。仅测试模式，无正式扣款入口。

会员 / 支付代码与 PostgreSQL / S3 迁移已提交为 69fc9e6。公开站点仍返回测试支付关闭、Stripe / PayPal 未启用，正式售卖关闭；数据迁移不代表支付商户联调完成。最新本地证据见 [会员与支付验收](validation-2026-11-10-membership-billing-v2.md)，云端状态与接续见 [交接](HANDOFF-2026-11-10-TOC-BILLING.md)。配置缺项为最近一次本地检查结果，后续执行前须重新检查，不能据此推断当前商户账户状态。

## 已实现与尚待验收

- Stripe Checkout：AUD/USD 卡（钱包符合条件时显示 Apple Pay），月度订阅；七天卡单次付款。
- Stripe Alipay：CNY 单次七天或一个日历月，到期手动续购。没有支付宝自动代扣。
- PayPal Sandbox Orders/Captures/Refunds：AUD/USD 单次七天或一个日历月，到期手动续购。本批不实现 PayPal 自动订阅。
- 服务器拥有价格；客户端不能指定金额、会员到期时间或额度。未付款不发权益。
- Stripe 月付以成功付款的 invoice 为独立周期，账期从渠道读取；失败续费不延长。单次月付按付款时间加一个日历月（月末截到有效日期），不是固定三十天。
- 每笔付款对应独立 grant 和用量周期。重复通知/重试不会重复发额度，退款后旧付款通知不复活权益。
- 支持取消 Stripe 自动续费并保留已付周期；测试客户门户可查看账单/更新付款方式。当前不支持自动中途升降级、优惠券、跨币种切换或叠加购买。
- Stripe 原始回调 HMAC 与时间校验；PayPal 调用 Sandbox 官方 verify-webhook-signature。通过验签后再读渠道当前对象，防止旧通知倒退状态。浏览器返回不是付款凭证。
- 订单、付款、退款状态均持久化；付款创建不明超过二十三小时的旧订单停止自动重试，避免渠道幂等窗口过期后重复创建。
- **目前无商户测试凭据，因此仅完成自动化模拟渠道验收，尚未做真实 Stripe/支付宝/PayPal Sandbox 交易、退款或 Apple Pay 设备联调。**

## 退款规则（用户确认）

每笔付款后七天内且尚未使用该笔付费权益，可以申请全额退款。

1. 已成功普通 AI、深度分析、会员课程正文阅读均算使用；正在处理的额度也会阻止申请。
2. 失败释放的 AI、免费课程、历史报告阅读和公共简报不算付费使用。
3. 以申请时刻判断七天窗口；管理员审核可以在窗口后完成。续费每笔独立判断，上一期用过不自动排除新一期退款。
4. 用户申请后原子冻结该笔 grant，防止边退款边消费。管理员拒绝则恢复原到期日和剩余额度，不补时长。
5. 管理员批准后原路全额退款；涉及自动订阅时同时取消未来续费。只有渠道退款成功才标记成功并永久撤销对应权益。
6. 渠道 pending/网络结果不明保持冻结并可核对/重试原退款；失败后管理员核实渠道状态，可拒绝申请恢复权益。
7. 本批只提供全额申请。外部后台发生部分退款时暂停相应权益并标记人工核对；不自动猜测按比例减少额度。外部全额退款撤销对应权益。
8. 管理员权限取自服务端 BILLING_ADMIN_USER_IDS，普通用户不能申请别人的退款、查看他人账单或给自己审批。

本批没有后台扫描任务自动恢复所有异常订单。渠道回调会重试，用户/管理员也可点击核对；长期异常仍需人工核对渠道记录。尚未实现拒付/争议的完整仲裁流程，正式上线前继续补齐。

## 需要用户在本机配置的账户

不要把密钥发到聊天或前端。把以下配置填入项目根目录 `.env`，此文件被 Git 忽略；模板在 `.env.example`。

```dotenv
BILLING_TEST_ENABLED=1
STRIPE_TEST_SECRET_KEY=sk_test_...
STRIPE_TEST_WEBHOOK_SECRET=whsec_...
STRIPE_TEST_PORTAL_CONFIGURATION=bpc_...
PAYPAL_SANDBOX_CLIENT_ID=...
PAYPAL_SANDBOX_CLIENT_SECRET=...
PAYPAL_SANDBOX_WEBHOOK_ID=...
BILLING_ADMIN_USER_IDS=已登录退款管理员的账户ID
```

### 澳洲 Stripe 测试账户及支付宝

1. 使用澳洲商户 Stripe 的测试环境，取得 **sk_test_** 密钥。代码拒绝 sk_live_；不要用正式密钥替换。
2. 配置测试事件转发到 `http://127.0.0.1:8001/api/billing/webhooks/stripe`，本地可使用官方 Stripe CLI：
   `stripe listen --forward-to http://127.0.0.1:8001/api/billing/webhooks/stripe`
   将该次 listener 的 whsec_ 写入服务端；它与 Dashboard 的 webhook secret 可能不同。
3. 接收 checkout.session.completed、checkout.session.async_payment_succeeded、checkout.session.async_payment_failed、checkout.session.expired、invoice.paid、invoice.payment_failed、customer.subscription.updated/deleted、refund.created/updated/failed、charge.refunded。
4. 代码请求 API 固定 `2024-06-20`，读取其 invoice/subscription/payment_intent 字段。Webhook 只取稳定 ID 后重新查询，仍应将端点版本与该版本对齐做真实测试。
5. 启用测试支付宝支付方式；CNY 经 Stripe Alipay 接入，不是独立国内支付宝商户直连。正式支付宝资格/澳洲业务类别批准仍需另行确认。
6. 配置测试 Customer Portal，仅允许更新付款方式、查看账单和取消续费。**关闭套餐/价格切换及促销功能**，保存 bpc_ 配置 ID；服务端需该配置才创建门户。
7. Apple Pay 由 Stripe Checkout 和设备条件决定，本地按钮选择不保证钱包实际出现。需在支持设备/测试域名上另行验收。

### PayPal Sandbox

1. PayPal Developer 建立澳洲商户 Sandbox Business 账户和 Sandbox REST App；建立独立 Sandbox Personal 买家。
2. 填写 Sandbox Client ID、Secret。代码固定访问 `https://api-m.sandbox.paypal.com`，没有 live base URL 配置。
3. Webhook 指向可达的测试 HTTPS 域名 `/api/billing/webhooks/paypal`，订阅 CHECKOUT.ORDER.APPROVED、PAYMENT.CAPTURE.COMPLETED/PENDING/DENIED/REFUNDED。
4. 将该 Sandbox App 的 webhook ID 写入配置。localhost 不能直接接收 PayPal 云端回调，需要测试部署或经授权的测试转发；不要把 local 模式的免邮件登录服务直接暴露到公网。
5. 正式配置前必须完成来源/签名拒绝、买家批准后 capture、完整退款及异步回调验收。

### 退款管理员

登录后 `/api/account` 返回 `user.id`；将该 UUID 加入 `BILLING_ADMIN_USER_IDS`。管理员会员页显示测试退款队列、审核说明、批准/拒绝、核对渠道退款。
账户 ID 不是授权凭证，权限由服务端 allowlist 判断；不提供前端自助管理员开关。

## 本地验证清单

- 无密钥：三币种价格可查看、购买按钮说明渠道未配置、无伪造支付成功。
- 开通：未支付、异步 pending 不开通；paid 且金额/币种/归属正确才开通。
- 幂等：重复 Checkout 请求、重复/并发付款事件、重复退款审批只对应一次渠道操作/权益。
- 续费：成功新周期发新额度，失败不续期，取消后当前 grant 仍有效；过期恢复免费。
- 退款：七天内未用成功申请；超时、AI 使用、pending 分析、付费课程阅读拒绝；免费课程和失败 AI 不阻止。
- 安全：跨账户 404、非管理员 403、错误签名/过期签名/live 对象拒绝、付款金额或退款关联不匹配拒绝。
- 真正联调：待账户配置后再执行，不能把模拟测试数量当作支付渠道实测证明。

官方资料：
- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/api/refunds/create
- https://docs.stripe.com/billing/subscriptions/webhooks
- https://docs.stripe.com/payments/alipay
- https://developer.paypal.com/docs/api/orders/v2/
- https://developer.paypal.com/docs/api/payments/v2/

## 管理员支付检查与待确认订单

`/#admin` 新增「测试支付检查」，展示配置是否齐全、超过十五分钟的创建中 / 待确认订单及最近核对记录。仅账号管理员或退款管理员可访问；不会展示密钥或 Checkout URL。

「向渠道核对」只读取 Stripe / PayPal 当前状态，经现有验证同步本地结果；不会新建付款、主动 capture、发起退款或允许人工标记成功。无渠道编号的订单仍需先核实原创建请求，不强制关闭。退款审核权限仍由 `BILLING_ADMIN_USER_IDS` 单独控制。

无密钥检查命令：`.venv\Scripts\python.exe -X utf8 -m server.payment_operations`。配置存在不等于凭据有效或回调可达；实际沙盒验收仍需按上文流程逐项执行。2026-11-10 再次检查仍缺少全部商户测试配置，未进行真实沙盒付款，详见 [验收记录](validation-2026-11-10-membership-billing-v2.md)。
