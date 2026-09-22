# Phase 3 架构：安全数据分析 Agent 工作流

状态：已批准，等待实施。

## 1. 目标

Phase 3 将 Phase 2 已验收的 Analytics 应用用例接入 DeerFlow Agent，但不复制任何 SQL 安全逻辑：

```text
Lead Agent
  -> 读取经营分析 workflow skill
  -> 查询可访问数据源/指标目录
  -> 调用单一受控查询工具（内部 plan -> execute，token 不暴露给模型）
  -> 形成结构化 evidence
  -> 委派 Data Analyst 分析
  -> 委派 Reviewer 复核 evidence 与数字
  -> 使用现有 sandbox/artifact 工具生成报告
  -> Lead 返回摘要、风险、evidence ID 与下载链接
```

本阶段不新增数据库表、迁移、HTTP API、MCP datasource、前端页面、调度器、容器或依赖。
`analysis_reports` 索引与工作台 UI 在 Phase 4 交付；Phase 6 再做完整 E2E。

## 2. 核心方案

采用 App-owned Agent bridge：

- `app.analytics.agent` 可以 import 通用 Harness 的 tool/runtime context；Harness 不得静态 import App。
- 通过现有配置化 tool loader（`use: app.analytics.agent...`）加载工具，不向 Harness 写入业务域分支。
- Gateway 在 Analytics composition 完成后绑定不可变 `AnalyticsServices`；shutdown 清除绑定。
- 工具从服务器运行上下文读取 principal，参数中不存在 `principal_id`、limits、credential 或 plan token。
- 可行性门禁已证明 async tool、可信 principal 与 Lead tool group 均可复用；现有 general-purpose
  subagent 会继承父级 tool groups，因此批准一个通用、加法式最小 seam：
  `SubagentOverrideConfig.disallowed_tools`。它只允许 operator 为指定 subagent **追加** denylist，
  不能移除内置拒绝项；registry 将 override 与 builtin denylist 去重合并。该 seam 不 import
  Analytics、不修改 tool loader，也不增加业务专用开关。

## 3. 工具集合

只新增两个面向模型的工具，避免把内部端口逐个暴露。

### 3.1 `inspect_business_catalog`

无身份参数。以当前 principal 调用 `AnalyticsServices.datasources` 与 metrics catalog，返回：

- 可访问 datasource：`id/name/engine/default_schema/status`；
- 当前 principal 可用 metric：`key/name/description/dimensions/version/status`；
- 不返回 owner、`secret_ref`、schema 全量、policy、credential 或内部版本。

### 3.2 `query_business_data`

模型参数严格只有：

```text
datasource_id: str
sql: str
```

一次工具调用内部顺序：

1. 从可信运行上下文取得 principal；
2. 调用 `PlanAnalyticsQuery`；
3. 仅在 `plan_created` 时把 receipt 中的 token 保留在局部变量；
4. 立即调用 `ExecuteAnalyticsQuery`；
5. 返回稳定 code、有界结果与安全 evidence；
6. 无论成功或失败，工具输出、日志、异常和模型消息都不包含 plan token。

不得把 plan/execute 做成两个 Agent 工具，否则一次性 capability token 会进入 ToolMessage、checkpoint
和 run event。工具也不得 import secret resolver、database runtime、repository 或 SQLAlchemy。

## 4. Evidence 契约

Phase 3 为成功执行返回一个不可变、安全且可 JSON 序列化的 evidence envelope：

- `evidence_id`：安全 envelope 的 canonical JSON SHA-256；
- `datasource_id`、`query_hash`、`risk`、`schema_version`、`policy_version`；
- `plan_digest`、estimated rows/cost；
- `row_count`、`byte_count`、`truncated`、`result_digest`；
- `decision_code`。

`result_digest` 对 canonical columns+rows 计算 SHA-256，用于 Reviewer 检测转述内容是否对应当前结果；
它不替代原始结果。返回对象可以携带受限 columns/rows 供模型分析，但 evidence 元数据不得携带 SQL、
token/digest、secret、DSN、异常文本或隐藏 PII。HIGH/PII 仍由 Phase 2 默认拒绝。

为生成这些字段，允许扩展 `QueryPlanDelivery` 的安全元数据，但 HTTP response 不必新增字段；API DTO
继续显式选择公开字段，不能通过 `model_dump()` 顺带泄漏内部 delivery 对象。

## 5. 工作流 Skill

新增中文优先的 public skill `skills/public/business-analysis/`，指导 Lead：

1. 先确认分析问题、时间范围、指标口径；信息不足时使用现有 clarification 能力；
2. 调用 catalog，选择 exact datasource/metric；
3. 一次只执行一个 `query_business_data`，禁止并行数据库查询；
4. 将工具返回的结果与 evidence 交给现有 general-purpose subagent，明确其角色为 Data Analyst；
5. Analyst 只做统计、对比、制图建议，不得虚构缺失数据；
6. evidence 就绪后再委派 Reviewer；Reviewer 不查询数据库、不创建子 Agent，只核对数字、口径、
   `result_digest`/evidence 引用与风险；
7. Reviewer 拒绝时最多允许一次定向修订；仍不通过则如实返回失败，不伪造通过；
8. 通过后使用现有 sandbox 写入 Markdown/CSV/图表 artifact，并由现有 `present_files` 交付；
9. 最终响应包含摘要、限制、风险、evidence ID 和 artifact 链接，不展示 chain-of-thought。

Skill 不包含固定表名、示例真实 SQL、凭据或 PII，不把 prompt 规则伪装成安全边界。

## 6. 运行与故障语义

- services 未绑定、无 principal、Analytics disabled/memory：工具返回稳定 `analytics_unavailable`。
- policy/authorization/plan/execute 拒绝：原样返回稳定 code，不泄漏异常文本。
- plan 成功但 execute 失败：token 已被消费；不重试，不重新 plan。
- 取消必须传播；工具不得在取消后启动第二次查询。
- tool output 由既有 SSE 工具事件承载，只包含结构化输入状态/稳定结果，不新增思维链事件。
- 子 Agent 失败沿用 DeerFlow 现有 task receipt、timeout、token budget、loop detection；skill 要求 Lead
  明确报告失败或进行唯一一次 reviewer 修订。

## 7. 配置与可用性

- `config.example.yaml` 增加 Analytics tool 定义和独立 tool group，为 Lead 启用。
- DeerFlow 当前会把父级 tool groups 继承给 general-purpose subagent；配置必须通过新增的
  `subagents.agents.general-purpose.disallowed_tools` 明确拒绝两个 Analytics 工具，使它们不进入
  Analyst/Reviewer 的实际 tool schema。
- `disallowed_tools` 是 operator-owned startup config，只能做加法拒绝；客户端/run context 不得覆盖。
- 现有配置升级路径必须能合并新增 tool/group；真实 `config.yaml` 仍保持 gitignored。
- `enabled=false` 或 memory backend 时工具可以被加载，但调用稳定失败；不得降级为直连数据库。

## 8. 验收

- Agent 工具参数不存在 principal/owner/limits/token/credential。
- 复用 Phase 2 application services，agent 模块无 SQLGlot/SQLAlchemy/driver/secret import。
- plan token 从未出现在 ToolMessage、checkpoint-shaped fixture、日志或异常。
- catalog 不返回 owner/secret_ref/policy。
- evidence ID/result digest 确定性、字段白名单与敏感字段拒绝有测试。
- HIGH、未授权表/列、DDL/DML、超限查询仍按 Phase 2 稳定拒绝。
- 同一工具调用只 plan 一次、execute 最多一次；execute 失败不自动重试。
- skill 通过现有 public skill reviewer/guidance 门禁。
- 通用 `disallowed_tools` 的默认兼容、加法合并、去重和 named-subagent 隔离有测试；Lead 仍能看到
  Analytics tools，而 general-purpose subagent 的实际 tool schema 中不存在它们。
- 不新增依赖、迁移、容器、API 或前端。

## 9. Phase 4 接力

Phase 4 消费本阶段的结构化 evidence 和现有 artifact：增加 Analytics 管理/分析工作台、运行轨迹、
报告索引与下载体验，同时完成 DeerFlow 品牌清理。不得在前端重新实现策略判定。
