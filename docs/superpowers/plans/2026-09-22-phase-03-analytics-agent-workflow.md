# Phase 3 Analytics Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过两个 App-owned 安全工具和一个经营分析 skill，让 Lead Agent 复用 Phase 2 查询闭环完成带 evidence 与 Reviewer 的分析工作流。

**Architecture:** Gateway 绑定 `AnalyticsServices` 到 App-owned agent runtime；配置化 tool loader 动态加载 catalog/query 工具。查询工具在一次调用内完成 plan+execute，绝不把 plan token 交给模型，并返回确定性的安全 evidence。

**Tech Stack:** Python 3.12、LangChain tools、DeerFlow runtime context、FastAPI lifespan、pytest、Ruff、现有 public skill review。

**Spec:** `docs/architecture/phase-03-analytics-agent-workflow.md`

## Global Constraints

- 起点 `c450c8c31b60b1f2276592a06318c5b33d2854e9`，固定 tag/tree 不变。
- 不新增依赖、数据库表、迁移、API、前端、MCP、容器或后台线程。
- Harness 不得静态 import App；Agent bridge 不得 import infrastructure database/secret/persistence。
- 只创建一个实现提交，TDD 证据写入忽略的 `.reviews/phase-03-implementation-report.md`。
- 生产 Python 新增/修改硬上限 16 个。只批准修改
  `deerflow/config/subagents_config.py` 与 `deerflow/subagents/registry.py` 增加通用 additive denylist；
  tool loader、task inheritance 与 builtin tool registry 不得修改。

## Planned Files

建议创建：

- `backend/app/analytics/agent/__init__.py`
- `backend/app/analytics/agent/runtime.py`
- `backend/app/analytics/agent/evidence.py`
- `backend/app/analytics/agent/tools.py`
- `skills/public/business-analysis/SKILL.md`
- `backend/tests/test_analytics_agent_runtime.py`
- `backend/tests/test_analytics_agent_evidence.py`
- `backend/tests/test_analytics_agent_tools.py`
- `backend/tests/test_business_analysis_skill.py`

建议修改：

- `backend/app/analytics/application/delivery.py`（只增加安全 evidence 所需元数据）
- `backend/app/analytics/composition.py`
- `backend/app/analytics/AGENTS.md`
- `backend/app/gateway/app.py`
- `backend/app/gateway/AGENTS.md`
- `backend/packages/harness/deerflow/config/subagents_config.py`
- `backend/packages/harness/deerflow/subagents/registry.py`
- `backend/tests/test_analytics_delivery.py`
- `backend/tests/test_analytics_composition.py`
- `backend/tests/test_subagent_tool_overrides.py`
- `config.example.yaml`
- `backend/docs/CONFIGURATION.md`
- `README.md`
- `docs/PROGRESS.md`
- 本计划与对应 prompt（原样提交）。

可行性门禁结论已记录：动态 async App tool、Lead tool group、可信 principal 均成立；general-purpose
会继承父级 tool groups。按已批准的 additive `disallowed_tools` seam 解决最后一项，不再重复停工。

### Task 1: Evidence 契约

- [ ] 先写 RED：canonical JSON、字段白名单、稳定 `evidence_id`/`result_digest`、NaN/未知类型拒绝。
- [ ] 实现不可变 `AnalyticsQueryEvidence` 与安全 tool result DTO；不得保存 raw SQL/token/secret。
- [ ] 扩展 `QueryPlanDelivery` 只携带 evidence 必需的安全元数据；HTTP DTO 显式字段保持不变。
- [ ] 验证同输入同 digest、任一安全字段/结果变化会改变相应 digest。

### Task 2: Startup-only service binding

- [ ] 写 RED：未绑定/重复绑定/清除、disabled/memory、无 principal 全部稳定失败。
- [ ] `runtime.py` 仅保存不可变 `AnalyticsServices | None`，Gateway lifespan 成功装配后绑定、finally 清除。
- [ ] 不创建 engine/session/repository，不缓存 principal，不 dispose 共享资源。

### Task 3: Catalog tool

- [ ] 写工具 schema RED，证明模型参数为空且输出无 owner/secret_ref/policy/version internals。
- [ ] 从可信 `get_effective_user_id()` 取得 principal，调用已绑定 catalogs。
- [ ] 只返回可访问 datasource 与 principal-owned metric 的白名单字段、确定性顺序。
- [ ] 未绑定/异常统一稳定 code，不包含异常文本。

### Task 4: Composite query tool

- [ ] 写 schema RED：参数恰为 `datasource_id`、`sql`，extra 字段拒绝。
- [ ] 写事件序列 RED：plan 一次；仅 plan_created 时 execute 一次；失败/取消绝不重试。
- [ ] 在局部变量持有 plan token，execute 后丢弃；tool return/repr/log/checkpoint-shaped fixture 全部扫描不到 token。
- [ ] 成功返回 bounded rows + evidence；拒绝只返回 stable code 和必要安全元数据。
- [ ] 断言 agent tool 模块不 import SQLGlot、SQLAlchemy、drivers、secret resolver、repositories。

### Task 5: Tool loader 与 Lead-only 配置

- [ ] 使用现有动态 tool loader 配置 `inspect_business_catalog`、`query_business_data` 和独立 group。
- [ ] 先为 `SubagentOverrideConfig` 增加默认空的 `disallowed_tools`；字段必须是 operator-owned 配置，
      元素非空、去重，不能由 run/request context 覆盖。
- [ ] `registry.get_subagent_config` 将 override denylist 与 builtin `disallowed_tools` 做稳定、加法式去重
      合并；不能用 override 解除 `general_purpose.py` 的硬编码拒绝项，默认空配置行为不变。
- [ ] `config.example.yaml` 为 general-purpose 配置两个 Analytics tool 名的 denylist；Lead 仍获得
      Analytics group，Analyst/Reviewer 的实际 tool schema 不包含它们。
- [ ] 配置/version/upgrade 测试证明 sample config 严格可解析且无工具名冲突。
- [ ] 不修改 `task_tool.py` 的继承语义、`deerflow.tools.get_available_tools` 或 Harness builtin list。

### Task 6: Business analysis skill

- [ ] 编写中文优先 SKILL.md，严格遵守架构 §5 的顺序、一次 reviewer 修订和串行查询。
- [ ] 使用现有 general-purpose task 做 Analyst/Reviewer；Reviewer 不查询数据库、不创建子 Agent。
- [ ] 报告由现有 sandbox/present_files 生成；skill 不实现文件写入、SQL policy 或凭证访问。
- [ ] 运行 public skill reviewer、skill tests 与 guidance registry；不得用 waiver 掩盖 blocker。

### Task 7: 文档与最终门禁

- [ ] 更新 Analytics/Gateway guides、配置文档、README 和 PROGRESS；Phase 3 保持待 GPT 复验。
- [ ] focused tests：本阶段 tests + delivery/composition/boundary/config/guidance/skill review。
- [ ] Ruff 只覆盖改动文件；不跑 Docker/真实数据库/全套。
- [ ] `git diff --check`、敏感样本扫描、changed-file、lock/tag/tree 边界检查。
- [ ] 一个提交：`feat: add governed analytics agent workflow`；工作树干净，Phase 4 未启动。

## Acceptance Checklist

- [ ] 模型永远看不到 plan token/secret/principal override。
- [ ] Agent 与 HTTP 复用同一 Phase 2 安全闭环。
- [ ] evidence 可确定性引用且不含 SQL/PII/credential。
- [ ] Analyst/Reviewer 使用现有 subagent 能力，Reviewer 无查询工具且最多一次修订。
- [ ] 无 Harness 业务域耦合、无新持久化/基础设施、无前端范围。
