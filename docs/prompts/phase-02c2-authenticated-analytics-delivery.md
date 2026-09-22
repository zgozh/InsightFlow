# Phase 2C2 实施提示词：认证 Analytics 交付与 Gateway 装配

你是 InsightFlow Phase 2C2 实施工程师。完整阅读并逐项执行：

1. 根 `AGENTS.md`、`backend/AGENTS.md`；
2. `backend/app/analytics/AGENTS.md`、`backend/app/gateway/AGENTS.md`；
3. `docs/architecture/phase-02c2-authenticated-analytics-delivery.md`；
4. `docs/superpowers/plans/2026-09-22-phase-02c2-authenticated-analytics-delivery.md`；
5. 本提示词。

架构规格优先于计划，计划优先于你的偏好。严格 TDD，先记录真实 RED 再做最小实现。

## 起点与提交

- `HEAD` 必须为 `d42c69ff068e357488f216ff5010c325575de89b`，其 parent 为 2C1 Fix 01 `0fc32bd7faef7d6f1a7da1bf72cbc26fdbd0903f`。
- 开始时工作树只应有本计划与本提示词两个未跟踪文件。
- 固定 tag `upstream-v2.1.0-rc0` 保持 commit `609bfde0ced76ff0a58c02ff5c741df768f44502`、tree `2473c22e163a3879490848a7995eb2b7be7f6f50`。
- 只创建一个实现提交：`feat: deliver authenticated analytics api`。
- `.reviews/phase-02c2-implementation-report.md` 保持忽略，不提交。

## 不可突破的边界

1. principal/owner 只从现有认证上下文取得；请求同名字段必须拒绝。
2. API 只接受 raw SQL + datasource ID 或一次性 plan ID；不得接受 prepared/authorized/limits/version/credential。
3. raw SQL、plan token/digest、secret、DSN、用户名密码、结果单元格和原始 EXPLAIN 不进入日志、审计或错误。
4. 普通用户 datasource 响应不得出现 owner/secret_ref；任何响应不得出现 resolved credential。
5. owner 不是查询授权；管理员查询也必须拥有 exact principal policy。
6. HIGH 永不执行，不新增批准接口。
7. 必须复用 2C1 durable plan store/audit；memory backend 稳定 503，禁止对外使用内存 store。
8. HTTP router 不得直调数据库 gateway；Phase 3 以后必须能复用同一应用服务。
9. 不新增依赖、容器、数据库、Redis、队列、后台线程、Agent Tool、MCP、前端或自动 Schema 探测。
10. Harness 永不 import App；保持全部边界测试。

## 修改范围与预算

只允许计划 File Structure 列出的文件。必要文件不在列表时停止，报告文件、原因和最小扩展，不自行越界。

- 生产 Python 新增/修改硬上限 18 个。
- `backend/pyproject.toml`、`backend/uv.lock`、frontend、docker、现有 Analytics migration 禁止修改。
- 本计划与本提示词原样提交，不改写。
- 中文注释/docstring/复杂测试说明；不要逐行翻译式注释。

## 验证纪律

- 所有 `uv` 命令使用 `--locked`；必要时使用官方 PyPI index，绝不改 lock。
- 运行计划指定的 focused tests 和改动范围 Ruff；不跑整个上游测试套件。
- 本阶段不改 database runtime，因此默认不启 Docker、不重跑真实 PostgreSQL/MySQL 门禁；若你认为必须修改 runtime，先停止报告。
- 管理员授权必须发生在业务 body 使用和 repository 调用之前。
- FastAPI/Pydantic 验证错误必须用测试证明不回显 raw SQL 或 token。
- `git diff --check` 必须真实 exit 0；不得再次误报。

## 完成回复

用中文报告：

1. commit、parent、message、文件统计与生产 Python 文件计数；
2. 配置/生命周期、管理用例、plan/execute 编排、认证 API、审计读取的实现摘要；
3. RED/GREEN 与最终 focused/Ruff 命令、退出码、计数；
4. principal/owner 绑定、raw SQL/token/credential 脱敏、memory 503、一次性 claim 的证据；
5. lock、固定 tag/tree、保护目录、工作树状态；
6. 所有偏差；没有写 `None`；
7. 明确写“Phase 3 未启动，等待 GPT 复验”。

不要自行宣告 Phase 2 完成，不要继续 Phase 3。
