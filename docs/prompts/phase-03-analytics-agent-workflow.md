# Phase 3 实施提示词：安全数据分析 Agent 工作流

你是 InsightFlow Phase 3 实施工程师。严格阅读并执行：

1. 根、backend、Analytics、Gateway 与 skills 目录下适用的 `AGENTS.md`；
2. `docs/architecture/phase-03-analytics-agent-workflow.md`；
3. `docs/superpowers/plans/2026-09-22-phase-03-analytics-agent-workflow.md`；
4. 本提示词。

## 起点

- `HEAD` 必须是已验收的 Phase 2C2 Fix 01：`c450c8c31b60b1f2276592a06318c5b33d2854e9`。
- 开始时工作树只应有上述架构、计划、提示词三个未跟踪文件。
- 固定 tag `upstream-v2.1.0-rc0` 的 commit/tree 不变。
- 一个实现提交：`feat: add governed analytics agent workflow`。

## 可行性门禁裁决

已确认：async App tool、Lead tool group、可信 principal 三项成立；general-purpose subagent 会继承
父级 tool groups，现状不能隐藏 Analytics tools。

批准方案 A：

- 在 `backend/packages/harness/deerflow/config/subagents_config.py` 的 `SubagentOverrideConfig` 增加
  operator-owned `disallowed_tools`；
- 在 `backend/packages/harness/deerflow/subagents/registry.py` 将它与 builtin denylist 做稳定、去重、
  **只增不减**的合并；
- 默认空值完全保持现有行为；override 不能解除任何硬编码拒绝项；
- 在 `config.example.yaml` 为 general-purpose 拒绝 `inspect_business_catalog` 与
  `query_business_data`，并用实际 tool schema 测试证明 Analyst/Reviewer 看不到它们。

不得修改 `task_tool.py` 继承语义、tool loader、Harness builtin list，不得增加 Analytics 专用 Harness
开关、全局万能 registry 或运行时“工具可见但调用时拒绝”的伪隔离。

## 安全边界

- Agent 查询工具参数只能是 `datasource_id + sql`；catalog 工具无身份参数。
- plan 与 execute 必须在一次工具调用内完成，plan token 只存在于局部变量，绝不进入模型消息、
  ToolMessage、checkpoint、run event、日志、异常或 evidence。
- principal、limits、policy/schema version、credential 全部服务端派生，模型不能提交。
- Agent bridge 只能调用 `AnalyticsServices` 应用入口，不 import SQLGlot/SQLAlchemy/driver/secret/repository。
- evidence 不含 raw/canonical SQL、token/digest、secret、DSN、异常文本或 PII；结果仍受 Phase 2 caps。
- HIGH/DDL/DML/越权/超限语义不变；execute 失败不自动重新 plan。
- Reviewer 无 Analytics tool、不创建子 Agent，拒绝后最多一次修订。
- 不新增依赖、迁移、表、API、MCP、前端、容器、队列或后台线程。

## 实施与验证

- 严格按计划 TDD；RED/GREEN 写入忽略的 `.reviews/phase-03-implementation-report.md`。
- 所有 `uv` 使用 `--locked`，不得修改 lock。
- 只跑 focused offline tests、改动范围 Ruff、skill reviewer/guidance、`git diff --check`。
- 不跑整个上游套件、Docker 或真实数据库；Phase 2 已提供数据库证据。
- 生产 Python 新增/修改不超过 16 个；除已批准的两个 Harness seam 文件外，必要文件不在计划列表时
  停止报告，不自行扩大范围。
- 架构、计划、提示词原样提交；`docs/PROGRESS.md` 保持 Phase 3 等待 GPT 复验，Phase 4 不启动。

## 最终回复

用中文报告：commit/parent/文件统计、tool seam 证明、工具参数与事件序列、token 敏感样本扫描、
evidence 契约、Lead-only 配置、skill/Reviewer 流程、RED/GREEN 与 focused/Ruff 计数、lock/tag/tree/
工作树状态、全部偏差。明确写“Phase 4 未启动，等待 GPT 复验”。

不要自行宣告 Phase 3 或整个项目完成。
