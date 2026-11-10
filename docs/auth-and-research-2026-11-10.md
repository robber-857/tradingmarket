# 登录注册与研究输出更新

## 财报和基本面

两类研究使用独立长文 schema，不改变新闻、宏观和期权的既有格式。普通模式目标为六百至九百汉字；深度模式要求结论和六至七个主题，每段至少 220 个字符，目标约一千四百至二千二百汉字。字符包含占位符，最终显示字数可能略有差异。

先解释经营与投资含义，再讲数据、估值情景和判断改变的条件；财报重点是增长、盈利质量、现金、资本投入及风险。基本面重点是经营质量、持续增长、价格与条件价值、情景和跟踪信号。没有行情或一致预期时不编造价格吸引力或超预期判断。

所有数值继续使用服务器证据占位符；正文已有的有效占位符会自动补入可点击引用列表。未知或缺失数字依然拒绝。切换分析深度会重置当前解读，避免把旧普通结果当作深度报告。历史保存内容不会自动重写。

## 账户

- `/#login`、`/#register`：登录／注册切换、Google 入口、邮箱必填、手机号选填。邮箱采用一次性链接，不存储密码。
- 邮箱验证完成前不创建个人资料；手机号不作为已验证联系方式或权限依据。
- Google 使用服务端授权码交换、PKCE、一次性 state 和 HttpOnly 浏览器绑定 cookie。仅接受 Google 已验证邮箱，按稳定 subject 绑定；已有非 Gmail/Workspace 邮箱账户必须走邮箱验证，不直接合并。
- 会话使用服务端保存的令牌哈希，浏览器只持有 HttpOnly / SameSite=Lax cookie；公网增加 Secure。退出后删除服务端会话。
- `next` 只接受站内页面白名单；验证后回到原页面，默认总览。401 会把账户及财报研究请求引导至登录页；会员、管理员、研究记录和会话归属仍由服务端检查。
- 本地模式继续允许单人匿名研究；公网 AI 必须登录，并受既有额度控制。

## 上线配置

1. 在目标 PostgreSQL 执行 `supabase/migrations/202611100002_auth.sql`，新增待验证元数据、手机号资料及 Google 身份映射表，均启用 RLS。应用通过既有服务端数据库连接访问。
2. 后端设置 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`，不得使用 VITE 前缀。Google Web OAuth 客户端授权回调必须精确为 `CLARORA_PUBLIC_URL/api/auth/google/callback`。
3. 设置 SMTP_HOST、SMTP_FROM、SMTP_PORT、SMTP_USER、SMTP_PASSWORD 和 EMAIL_LOGIN_ENABLED=1；公网 CLARORA_MODE=public、CLARORA_PUBLIC_URL 必须为实际 HTTPS 域名。
4. 分别真实验证 Google 同意/取消、邮件送达、链接一次性、退出和原页面返回。未配置的通道在界面中明确禁用。

实现参考：[Google 服务端 OAuth 文档](https://developers.google.com/identity/protocols/oauth2/web-server)。视觉参考：[Login UI with Multiple Auth Options](https://dribbble.com/shots/25747592-Login-UI-with-Multiple-Auth-Options)，采用登录注册切换与多认证入口，保留霁明品牌。

## 验证记录

- 完整后端回归：357 passed，7 skipped（包括需要独立 PostgreSQL 的检查）；最后调整后财报与认证专项 40 passed。前端生产构建通过。
- Chrome 实际验证本机邮箱注册、一次性验证和返回 `#financials`；桌面及 390px 手机布局已查看。
- 本机 Google OAuth 凭据 / SMTP 应用密码均未配置，真实 Google 登录和邮件送达未验收。Google 上游行为以模拟响应覆盖 state、浏览器绑定、重放、未验证邮箱拒绝。
- 本次未部署公网、未执行生产迁移。浏览器 QA 账户 `auth-qa-20261110@example.com` 只在本地，测试完成已退出。

- 真实 OpenAI 基本面深度生成通过：六个分析主题，加综合结论共 1,506 个正文字符；数值和引用校验通过。财报真实生成也通过；最终深度篇幅规则另有专项测试。深度研究等待上限调整为 240 秒（部署函数上限现为 300 秒）。

- 用户指定 SMTP 发件邮箱为 eltonw482@gmail.com：已写入本机私有 .env 的 SMTP_FROM / SMTP_USER，主机 smtp.gmail.com、端口 587（STARTTLS）；仍缺应用密码。缺认证密码时公网邮件入口不启用。后续认证与会员专项 16 passed、1 skipped。

- 后续用户已填写 SMTP_PASSWORD，使用 Gmail STARTTLS 的真实身份验证成功；本轮未发送测试邮件。Google Cloud 中 Clarora 品牌位于 Growshare 项目 onyx-nexus-514209-c7，Web 客户端表单已准备，待创建前确认。

- Google OAuth 后续配置：用户确认使用独立项目 `clarora`（不是 Growshare）。已在该项目创建 Clarora 应用及 Clarora Web Login Web 客户端；回调为本机 127.0.0.1:5173 和现有 Vercel 域名的 /api/auth/google/callback。凭据只写本机私有 .env，/api/auth/config 已返回 google=true。应用仍为 External / Testing；测试用户名单变更等待明确授权，真实登录待完成。

- Google OAuth 真实联调完成（2026-11-10）：用户明确授权后，将 eltonw482@gmail.com 加入项目 clarora 的测试用户名单。Chrome 从本机 /#login?next=membership 发起 Google 登录，选择该邮箱，授权页只请求邮箱，成功回调到 /#membership 并显示该邮箱及账户额度。真实登录已验证；Google 仍为 External / Testing，公网部署、生产环境变量和生产迁移尚未在本轮执行。


## Production rollout (2026-11-10)

- Production: https://clarora-market-research.vercel.app; Vercel deployment dpl_HedSawVQv1qaQKRfm9T7XGX9DTn3.
- Applied 202611100002_auth.sql transactionally to Supabase bemxbmbtvttirklkpmjx, clarora schema. Three auth tables verified with RLS enabled; existing user count unchanged. No local database import.
- Uploaded server-only Google OAuth and SMTP configuration; EMAIL_LOGIN_ENABLED=1, public mode verified, no secrets in source. Sender: eltonw482@gmail.com.
- Google project clarora published as External / In production after explicit user approval. Scope: openid email. Homepage and privacy URL configured.
- Online email registration delivered a real message to the owner-controlled plus alias; optional phone left empty; fresh-tab email-link login reached membership with free 5/1 quotas. Logout returned anonymous state. Consumed token replay returned 400. Initial same-tab automation attempt consumed a token without retaining the browser session; subsequent fresh-tab flow completed successfully.
- Cross-origin mutation returned 403; unauthenticated account returned no user; public config returns Google/email enabled and local=false. Privacy page returns 200.
- Auth/membership tests: 16 passed, 1 skipped (external integration prerequisite). Production Vite builds passed.
- QA account eltonw482+clarora-qa@gmail.com is retained as a free account; no paid grant or purchase.
- Production Google sign-in completed using eltonw482@gmail.com; callback reached #membership and displayed the correct signed-in account and entitlements. Third-party accounts were not impersonated or tested; public eligibility is confirmed by Google In production status.
