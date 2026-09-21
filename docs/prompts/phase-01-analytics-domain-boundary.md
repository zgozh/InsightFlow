# Phase 1 实施提示词：Analytics 领域边界

你是 InsightFlow Phase 1 的实施工程师。严格执行已经批准的实施计划，不重新设计架构，不扩展范围。

## 当前已验收状态

- 工作目录：`D:\develop\workspace\InsightFlow`
- 当前 HEAD 必须是：`aa516bd4f1120aafaa00a9ce1f5105fcda5cf2b3`
- 不可变基线 tag：`upstream-v2.1.0-rc0`
- 基线 commit：`609bfde0ced76ff0a58c02ff5c741df768f44502`
- 基线 tree：`2473c22e163a3879490848a7995eb2b7be7f6f50`
- Phase 0 已通过架构复验。

开工前必须完整阅读：

1. `AGENTS.md`
2. `backend/AGENTS.md`
3. `docs/architecture/architecture-refactoring-report.md`
4. `docs/decisions/0001-insightflow-hard-fork.md`
5. `docs/superpowers/plans/2026-09-21-phase-01-analytics-domain-boundary.md`

Phase 1 plan 是本轮唯一施工规格。逐项执行，不得跳过 RED/GREEN 证据和完整回归门禁。Plan 与本提示词由架构师提供，只读，不得自行修改内容。

## 本轮目标

建立一个小而真实、可测试的 `app.analytics` 领域边界：

- 不可变 datasource 领域契约。
- 不可变 metric 领域契约。
- async datasource/metric application ports。
- 自动化依赖边界测试。
- 本地 `AGENTS.md` 约束。

这不是“把所有五层空目录先建出来”。只有本轮有真实接口和测试的 `domain`、`application` 可以创建；`infrastructure`、`agent`、`api` 必须留给后续阶段的真实功能。

## 允许修改/新增

- `backend/app/analytics/AGENTS.md`
- `backend/app/analytics/__init__.py`
- `backend/app/analytics/domain/__init__.py`
- `backend/app/analytics/domain/datasource.py`
- `backend/app/analytics/domain/metric.py`
- `backend/app/analytics/application/__init__.py`
- `backend/app/analytics/application/ports.py`
- `backend/tests/test_analytics_domain.py`
- `backend/tests/test_analytics_boundaries.py`
- `docs/PROGRESS.md`
- 提交架构师已创建但不得改写的 Phase 1 plan 和本提示词
- 本地创建 `.reviews/phase-01-implementation-report.md`，保持忽略、不提交

## 严禁事项

- 不得修改 `backend/packages/harness/**`。
- 不得修改 Gateway、router、runtime、middleware、subagent registry。
- 不得新增数据库、ORM、migration、SQL parser、SQLGlot 或 datasource 连接。
- 不得新增 API、Agent、Tool、MCP、UI、Docker 服务。
- 不得修改依赖清单、lockfile、config、README 或 LICENSE。
- 不得创建空的 `infrastructure/`、`agent/`、`api/` 目录。
- 不得把密码、DSN、host、username 放进领域模型；只允许 opaque `secret_ref`。
- 不得改名 `deerflow.*`。
- 不得 amend Phase 0 提交，不得移动基线 tag。
- 不得安装或更新依赖。

## 施工纪律

1. 先验证 HEAD、tag、tree 和工作树；除本 plan 和本提示词外出现其他未提交路径时立即停止。
2. 先创建测试并运行一次真实失败，预期因 `app.analytics` 尚不存在而 collection failure。
3. 记录 RED 命令、退出码和实际 `ModuleNotFoundError`。
4. 按 plan 给出的接口和约束实现最小代码，不额外增加 service、repository implementation 或抽象基类。
5. 运行 focused GREEN、Ruff、完整 backend test、blocking-I/O 和 lint。
6. 任何完整门禁失败都不得声称 PASS；不要修改无关上游代码来掩盖失败。
7. 只创建一个提交：

```text
feat: establish analytics domain boundary
```

8. 提交后写本地 review report，然后停止，不得开始 Phase 2。

## 必须重点验证

- `domain/` 只能依赖标准库和自身 domain 模块。
- `application/` 可以依赖 domain，但不能依赖 Gateway、Harness、FastAPI、LangChain、SQLAlchemy。
- 现有 `test_harness_boundary.py` 继续证明 Harness 不 import App。
- datasource 对象没有 `password` 或 `dsn` 字段。
- metric key、version、dimensions 的不变量都有测试。
- 不存在 dependency/lockfile、migration、route、UI、Docker 或 Harness Diff。

## 最终回复格式

```text
PHASE 1 RESULT: PASS | FAIL

Commit:
- <full hash or NONE>
- Parent: <hash>

Changed files:
- <path — purpose>

TDD evidence:
- RED command: <exact command>
  Exit code: <number>
  Failure: <actual key output>
- GREEN command: <exact command>
  Exit code: <number>
  Result: <actual test totals>

Regression gates:
- <exact command>
  Exit code: <number>
  Key output: <actual output>

Boundary check:
- Harness changed: NO
- Gateway/routes changed: NO
- Dependencies/lockfiles changed: NO
- Database/migrations changed: NO
- UI/Docker changed: NO
- Baseline tag changed: NO
- Phase 2 started: NO

Deviations:
- None | <exact deviation and reason>

Review artifact:
- .reviews/phase-01-implementation-report.md
```

只报告真实执行结果。不得把未运行、跳过、超时或失败的命令写成 PASS。
