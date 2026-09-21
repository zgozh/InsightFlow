# Phase 2C1 实施提示词：持久化 Analytics 控制面

你是 InsightFlow Phase 2C1 的实施工程师。直接在当前 `main` 工作，不重新设计总体架构，不扩展到 Phase 2C2。

## 1. 必读文件

开始前完整阅读并遵守：

1. 根 `AGENTS.md`
2. `backend/AGENTS.md`
3. `backend/app/analytics/AGENTS.md`
4. `backend/packages/harness/deerflow/persistence/migrations/AGENTS.md`
5. `docs/architecture/phase-02c1-durable-analytics-control-plane.md`
6. `docs/superpowers/plans/2026-09-22-phase-02c1-durable-analytics-control-plane.md`
7. 本提示词

架构规格优先于施工计划，施工计划优先于你自己的偏好。发现矛盾、安全缺口或必须越界时立即停止并报告，不得静默改规格。

## 2. 起点与提交纪律

- `HEAD` 必须是 `456b57a302b5fe95531a43b11361653a1a8e7d8f`。
- parent 必须是已验收的 Phase 2B2 Fix 01：`09cbd28a49e2718ff4d72c52a3ae49e78ce295d1`。
- 固定 tag `upstream-v2.1.0-rc0` 必须保持 commit `609bfde0ced76ff0a58c02ff5c741df768f44502`、tree `2473c22e163a3879490848a7995eb2b7be7f6f50`。
- 开始时工作树应只有本计划与本提示词两个未跟踪文件；不得覆盖或丢弃它们。
- 实施只创建一个最终提交：`feat: add durable analytics control plane`。RED/GREEN 过程写入忽略的 `.reviews/phase-02c1-implementation-report.md`，不创建中间提交。
- 完成后工作树必须干净。

## 3. 实施方式

严格逐任务执行计划，使用 TDD：先写能因缺失行为而失败的精确测试，记录 RED 命令、退出码和关键错误；再做最小实现并记录 GREEN。不要伪造 RED，不要通过放宽断言、跳过普通测试或复制生产算法到测试来变绿。

注释、docstring、复杂测试说明、文档和报告以中文为主；标识符、协议、枚举值和数据库名保持英文。不要批量翻译未触及的上游文件。

## 4. 不可突破的安全边界

1. Analytics 使用独立 `AnalyticsBase`、独立 Alembic 链和 `analytics_alembic_version`，但复用现有应用数据库；不得注册进 Harness `Base.metadata`。
2. Harness 不得 import `app.analytics`。Analytics infrastructure 不得 import Harness、Gateway、FastAPI 或 LangChain。
3. SQL plan claim 必须由数据库单条 `DELETE ... RETURNING` 原子消费；禁止 SELECT-then-DELETE、dict 或 `asyncio.Lock`。
4. 错 principal、过期、已领取、损坏和未知 payload version 都必须消费 token 并统一得到 `PLAN_UNAVAILABLE`。
5. 原始 token 永不落库；只存 SHA-256 digest。不得记录 digest。
6. plan payload 只允许 canonical prepared SQL、opaque `secret_ref` 和重建 immutable plan 所需值，最大 1 MiB、TTL 最大 300 秒；不得包含已解析凭证或原始用户 SQL。
7. query audit 不得含任何 SQL、token/digest、secret ref、DSN、账号密码、驱动异常文本、原始 EXPLAIN 或结果值。
8. audit start 失败时不得访问业务数据库；audit finish 失败不得返回 plan token 或查询结果。执行审计失败后留下 `started` 是保守证据。
9. owner 不自动获得 datasource 查询权限；必须有 exact principal policy。不得以 `None` 表示跨用户查询，不得增加通配 principal。
10. schema/policy 更新必须使用 `expected_version`，同版本不同内容和 stale expected 都拒绝。
11. memory backend 不得对外伪装成持久化控制面。
12. 不新增依赖、中间件、数据库、Redis、队列、容器或后台线程。

## 5. 允许修改范围

只允许修改施工计划“File Structure”列出的文件，以及创建：

- `.reviews/phase-02c1-implementation-report.md`（必须保持忽略、不得提交）；
- `docs/superpowers/plans/2026-09-22-phase-02c1-durable-analytics-control-plane.md`（原样提交）；
- `docs/prompts/phase-02c1-durable-analytics-control-plane.md`（原样提交）。

明确禁止：

- 修改已批准的 `docs/architecture/phase-02c1-durable-analytics-control-plane.md`；
- 修改 `backend/pyproject.toml`、`backend/uv.lock`；
- 修改 `backend/app/gateway/**`、配置 schema、前端、Docker Compose；
- 添加 API、Gateway composition、Agent Tool、MCP、Phase 2C2/3 功能；
- 修改 Phase 2A/2B1 的默认拒绝策略或放宽 Phase 2B2 数据库执行限制。

如果某个必要文件未在允许集合中，停止并只报告文件、原因和最小扩展建议，不要自行扩大范围。

## 6. 环境与门禁

- 所有 `uv` 命令使用 `--locked`；必要时设置 `UV_DEFAULT_INDEX=https://pypi.org/simple`，防止本机镜像配置触发 lock 漂移。
- 按计划运行 focused offline suite、Ruff、migration tests 和 `git diff --check`。
- 普通测试不得依赖 Docker。
- 离线门禁全绿后，只运行一次 `python scripts/test_analytics_databases.py --engine all`。它必须复用现有 PostgreSQL 16/MySQL 8.4 服务并在 finally 销毁；不得新增服务或留下容器。
- 不需要重复运行整个上游全套测试。若 focused regression 与已有 2B2 证据矛盾，再报告并扩大验证。

## 7. 体量与偏差纪律

- 新增/修改生产 Python 文件不得超过 22 个；达到 22 前仍无法完成时停止报告。
- 不为每张表机械生成 controller/service/factory；按 catalog、codec、plan、audit、migration 职责组织。
- 规格外的“顺手重构”、格式化全仓、依赖升级、API 预埋均禁止。
- 技术事实迫使偏差时，在编码前停止；不得先做再解释。

## 8. 完成前边界检查

逐项证明：

- commit parent、message、changed-file 集合准确；
- 固定 tag/tree 未变；
- `backend/pyproject.toml` 与 `backend/uv.lock` 相对起点零变化，并报告 lock SHA-256；
- `backend/app/gateway/**`、frontend、Compose 零变化；
- plan token、SQL、credential、result value 未进入 audit schema、日志或异常；
- 两条 Alembic 链互不管理对方表；
- PostgreSQL 两个独立连接竞争 plan 恰好一个成功；
- audit start/finish fail-closed 测试成立；
- `docs/PROGRESS.md` 仍把 Phase 2 标为 `In progress`，next gate 为 `Phase 2C1 GPT 复验`；
- Phase 2C2 未启动；
- 工作树干净。

## 9. 最终回复格式

完成后用中文只报告：

1. 最终 commit hash、parent、message、文件统计；
2. 核心安全实现：迁移所有权、principal 隔离、原子 claim、审计门禁、敏感字段边界；
3. RED/GREEN、focused offline、Ruff、PostgreSQL/MySQL Docker 门禁的命令、退出码和计数；
4. PostgreSQL/MySQL 实际镜像版本及清理状态；
5. 依赖/lock、固定 tag/tree、工作树状态；
6. 生产 Python 文件预算；
7. 所有偏差；没有就写 `None`；
8. 明确写“Phase 2C2 未启动，等待 GPT 复验”。

不要自行宣告 Phase 2 完成，不要继续下一阶段。
