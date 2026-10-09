# 2026-10-07 AS-01 / AS-15 默认栈里程碑验证

## 结论

AS-01 认证门禁与 AS-15 默认四服务启动均达到本场景验收条件。已验证匿名拒绝、双主体 self 与 cross-owner 行为、默认栈健康/readiness 及真实分析入口；跨 owner 404 只反映请求方已提交的 A thread UUID，且与随机不存在 UUID 的错误形状一致，没有泄露资源标题或正文。SSE 完成后是否交付运行内容属于 AS-09，不阻塞 AS-01 认证门禁。本结论不表示 AS-01～AS-15、Phase 6 或发布整体完成。

本轮未修改生产代码或测试代码，未调用模型，也未提交或推送。运行记录和事件是明确标记的合成夹具，不是模型生成结果。

## 隔离默认栈

原 Compose 项目名 deer-flow 已存在且未运行。本轮没有启动或修改它，也没有触碰已有账号、容器或卷。使用独立 Compose 项目 as01-as15-1bf6932f3abd，并保留栈供下一里程碑继续使用。

启动入口为 .reviews/as01-as15-1bf6932f3abd/compose.ps1。配置检查通过；启动使用该脚本的 start 操作，实际调用 Compose up -d --no-build --pull never --wait。没有构建或拉取镜像。解析后的服务恰为 nginx、frontend、gateway、redis；四个容器均报告 healthy/running。唯一宿主机映射为 127.0.0.1:29385 → 容器 2026；Gateway 8001、Frontend 3000、Redis 6379 均未发布到宿主机。

本次使用镜像：

- Frontend：insightflow-analytics-demo-frontend:latest，sha256:18f137c24a8d55f15fde1de30d1bd9f0d367cb6f27b3ed04aa52f2a5bcb07430
- Gateway：iflow-6f3e2-b9c45a-gateway:latest，sha256:a2077298dd68b27c453808c64afab42569b3c6e66c165b4a0cc897e23ffd1c60
- Nginx：nginx:alpine，sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752
- Redis：redis:7-alpine，sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf

Gateway 容器的 SQLite 数据库实际路径为 /app/backend/.deer-flow/data/deerflow.db，由隔离目录 .reviews/as01-as15-1bf6932f3abd/app-home 挂载提供；宿主机数据库文件为 .reviews/as01-as15-1bf6932f3abd/app-home/data/deerflow.db。文件存在，读回确认有 runs、run_events、run_change_clock 表。隔离配置使用 SQLite 和数据库事件存储，没有配置模型。

测试账号凭据仅保存在当前 Windows 用户 DPAPI 保护的 .reviews/as01-as15-1bf6932f3abd/credentials.dpapi 中；Compose 环境文件为同目录 stack.env。git check-ignore 确认两个路径均被忽略。报告、终端输出和证据 JSON 未包含凭据值。临时目录中含本轮 runner、隔离配置与脱敏证据；不要清理该目录或隔离栈，后续切片仍需使用。

## AS-01：主体和资源 owner 边界

创建了两个独立主体：管理员 A 与普通用户 B。A 通过 initialize 创建，B 通过 register 创建；独立登录和 /me 均为 HTTP 200，角色分别为 admin、user。匿名 /api/v1/auth/me 为 401。登录响应没有在 JSON body 暴露 token。

A 的分析线程 ID 为 9e080128-aedc-44f5-9ece-4bf75692021e，持久化 kind=analysis 和 analysis_mode=true。B 的聊天线程 ID 为 ae9d5f3f-dc88-475c-a8fe-a14d0eb157f6。A、B 读取各自线程为 200，B 读取 A 的线程为 404；B 的线程搜索结果不包含 A 的线程 ID。A 读取自己的 artifact 为 200 且内容与合成夹具一致，B 跨 owner 读取为 404。

补充的只读 A/B/匿名 API probe 中，A/B 各自 thread 为 200，A 自有 artifact 为 200 且合成正文正向匹配；A admin datasource route 为 200，B 的 user datasource route 为 200。匿名读取 A thread、artifact、admin/user datasource route 分别为 401，拒绝响应不含 6 个现存合成 ID/path/body 标记。B 跨 owner thread 与 artifact 为 404，B admin datasource route 为 403。B 的 thread/artifact 404 body 会回显请求方已提交的 thread UUID；对随机不存在 thread 归一化 UUID 后错误形状相同，对随机不存在 artifact 错误 body 完全相同，因此没有资源存在性 oracle。A thread 没有可提取的 title marker，标题内容不可用/未测试；admin datasource list 为 0 条，没有行级值可作内容标记比较。响应正文只在进程内用于比较，没有打印或保存。

Run ID 为 synthetic-as01-916957be14f845a0abc7dbba6be6d772。它由 Gateway 持久化接口写入，owner 为 A，绑定 A 的 analysis 线程，状态为 success，并带有 synthetic_acceptance_fixture=true、model_called=false。夹具包含一个标记为合成的人类输入事件；没有模型调用或模型输出。

A 读取 run messages、run events 和 stateless run messages 均为 200；B 跨 owner 读取均为 404；匿名读取均为 401。SSE join 对 A 返回 200，但已完成的合成 run 只返回 end 事件，没有夹具内容；B 跨 owner 为 404，匿名为 401。这证明了本场景所需的 SSE owner/auth gate。已完成 run 的内容 replay 属于 AS-09 的运行交付验收，不是 AS-01 登录/隔离门禁的未完成条件。

## AS-15 与认证浏览器入口

Compose 的 --wait 成功，四个服务报告 healthy/running；数据库路径和实际 SQLite 文件如上。Playwright 访问未认证的 A 分析路径后被重定向到 /login。随后在浏览器请求上下文中使用 A 登录，登录响应为 200，/me 为 200 且角色为 admin，并观察到 access_token 与 csrf_token cookie 名称。

旧探针只监听 /api/threads/{id}，而实际 metadata 请求经 SDK 使用 /api/langgraph/threads/{id}；旧探针还用英文 placeholder 正则检查 composer，未等待数据加载完成。故前次 ownThreadApiStatus=null、composerVisible=false 是夹具断言错误，不能作为产品缺陷证据。

2026-10-07 修正 ignored runner 后进行一次有界真实浏览器采样：匿名 A 分析入口跳转 /login；A 登录及 /me 均为 200。A 自有 analysis metadata、history、messages 与 models 请求分别为 200，等到实际 DOM composer 可见且启用；/workspace/analysis/new composer 也可见且启用。A 访问 B 的聊天线程时 metadata 为 404，页面显示终态拒绝状态且没有 composer。pageerror=0、API requestfailed=0、POST /runs/stream=0。没有配置真实 key 或调用模型；GET /api/models 的 200 只表示目录请求成功，不代表配置了可调用模型。详见[AS-15 工作区诊断](2026-10-07-as15-workspace-diagnosis.md)。

## 定点检查

在 backend 目录执行以下 pytest 命令，结果为 17 passed、1 条 StarletteDeprecationWarning，耗时 21.44 秒：

    .\.venv\Scripts\python.exe -m pytest tests/test_compose_default_bind_host.py tests/test_compose_default_workers.py tests/test_auth_middleware.py::test_protected_path_no_cookie_returns_401 tests/test_auth_middleware.py::test_protected_post_no_cookie_returns_401 tests/test_stateless_runs_owner_isolation.py::test_stream_cross_user_returns_404 tests/test_stateless_runs_owner_isolation.py::test_wait_cross_user_returns_404_without_channel_values tests/test_auth_type_system.py::test_api_login_success_no_token_in_body tests/test_auth_me_permissions.py::test_initialize_response_leaves_permissions_unresolved -q

该组定点测试记录了早期边界与隔离脚本证据。另在 backend 目录执行 Gateway readiness 三个直接用例，设置 Windows Python UTF-8 模式后为 3 passed、exit 0：test_production_gateway_has_a_real_readiness_probe、test_deploy_waits_for_gateway_readiness_before_success、test_deploy_failure_prints_gateway_diagnostics_and_never_claims_success。未经修改的隔离 default Compose base 加命名/镜像/loopback/mount overlay 栈此前以 Compose --wait 启动成功，四服务 healthy，唯一宿主映射为 127.0.0.1:29385，SQLite 挂载存在；不将其误称为 root make up 原样命令。完整 API 状态记录位于隔离目录 api-evidence.json 与 run-evidence.json，新 no-leak 结果见工作区诊断报告。

AS-01 认证门禁与 AS-15 四服务默认启动均通过。readiness 测试首轮遇到宿主 Python GBK 解码 UTF-8 subprocess 输出失败，使用 PYTHONUTF8=1 重跑后 3 项通过；该过程没有修改脚本或产品代码。没有模型 key/调用、容器重启、配置改动、重新注册或重新 seed；没有提交或推送。AS-09 SSE 内容交付仍按其独立场景跟踪。
