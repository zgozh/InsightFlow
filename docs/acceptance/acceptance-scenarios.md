# InsightFlow 发布级验收场景

> 基线：DeerFlow `v2.1.0-rc0`（`upstream-v2.1.0-rc0`）
>
> 依据：[架构重构报告](../architecture/architecture-refactoring-report.md)
>
> 性质：发布级（release-level）验收契约。Phase 0 不交付运行时行为，因此本文件定义的是 Phase 1–6 必须满足的端到端验收口径，不随阶段重新解释。

每个场景在通过时必须提交：执行命令、退出码、关键输出与证据位置。只写「测试通过」不构成验收。

本文件描述目标发布验收，不自动表示当前代码已经具备或通过该场景。当前代码路径、测试 ID、命令实测和未覆盖范围以[Phase 6D1 契约对账矩阵](phase-06d-contract-reconciliation.md)为准；AS-14 目前仍是发布阻塞。

---

## AS-01 认证（authentication）

- **Given** 一个未认证的浏览器会话；系统内已存在用户与其他主体的 thread/run/artifact 数据
- **When** 访问 `/workspace/analysis/new` 或任意受保护的 Gateway API
- **Then** 请求被拒绝：前端跳转登录，API 返回未认证状态，且响应体中不包含任何 thread、run、datasource 或 artifact 数据
- **And Given** 用户已成功认证 **When** 进入分析工作台 **Then** 只能访问其有权访问的 thread/run/artifact，不返回其他主体的数据

依据：报告 §4 KEEP（Gateway Auth/Thread/Run/SSE/Artifact 主链）、§14 E2E（登录 → 配置 datasource → …）。

## AS-02 MySQL 数据源（MySQL datasource）

- **Given** 管理员已配置一个 MySQL 业务数据源（凭据经 secret provider 注入，库中不存明文），并为某用户授予 schema/table/column 白名单
- **When** 用户以自然语言提出一个可由该数据源回答的经营问题
- **Then** 系统以显式 `mysql` dialect 解析候选 SQL，生成只读查询计划并执行成功，返回有界结果集并写入 artifact
- **And** 结果与对同一问题直接执行等价只读 SQL 的结果一致；执行使用独立只读用户与只读事务

依据：报告 §10（显式 dialect 解析与只读执行）、§14 Integration（MySQL/PostgreSQL 测试库的 read-only 查询）、§17（方言差异需显式 dialect + 双库 fixture）。

## AS-03 PostgreSQL 数据源（PostgreSQL datasource）

- **Given** 管理员已配置一个 PostgreSQL 业务数据源与相应白名单
- **When** 用户以自然语言提出一个可由该数据源回答的经营问题
- **Then** 系统以显式 `postgres` dialect 解析并成功执行只读查询，返回有界结果集并写入 artifact
- **And** 涉及方言差异的构造（标识符引用、LIMIT/FETCH 语义等）在 PostgreSQL 下行为正确，且与 AS-02 的 MySQL 结果语义一致

依据：报告 §10、§14 Integration、§15（业务 PostgreSQL 与 Compose 运行时数据库相互独立）。

## AS-04 数据源/表/列越权拒绝（datasource/table/column denial）

- **Given** 用户仅被授权访问数据源 D 下 schema `s` 的表 `t` 中的列 `c1`、`c2`
- **When** 请求生成访问未授权数据源 D′、未授权表 `t′` 或未授权列 `c3` 的查询
- **Then** 策略层确定性拒绝，判定为 `BLOCKED` 并给出 decision reason；不签发可执行 query plan ID，且不产生任何发往数据库的执行
- **And** 该拒绝被写入 `sql_query_audits`（含 user/run/agent/datasource 标识、query hash、dialect、risk level、decision reasons）

依据：报告 §10（datasource/schema/table/column 白名单）、§11（`sql_query_audits`）、§14 Security（越权 datasource/schema/table/column）。

## AS-05 DDL/DML/多语句阻断（DDL/DML/multi-statement blocking）

- **Given** 一个已认证用户及其合法数据源授权
- **When** 候选 SQL 包含 DDL（CREATE/ALTER/DROP）、DML（INSERT/UPDATE/DELETE）、事务控制、多语句、文件或网络导出，或解析为通用 `Command`、无法解析、方言不确定
- **Then** 一律 fail closed：判定 `BLOCKED`，不执行，并返回可解释的决策理由
- **And** 通过注释、大小写、分号或 Unicode 变体尝试绕过时同样被拒绝
- **And** 只有单语句且 AST 根节点在允许集合内、序列化后可在同方言重新解析的输入才可能被放行

依据：报告 §10（黑名单、AST 根节点、序列化后重新解析、fail closed）、§14 Security（DDL/DML、多语句、注释绕过、`Command` fallback）。

## AS-06 超时与结果上限（timeout and result caps）

- **Given** 一个通过策略校验但成本较高的白名单 SELECT
- **When** 执行该查询
- **Then** 执行受 statement timeout 约束：超时以明确的错误类别结束并记录审计，不无限占用连接
- **And** 结果受 row cap 与 byte cap 约束，超出部分被截断而不返回，且截断事实在 run event 与审计中可见
- **And** `MEDIUM` 风险查询使用更低超时与更低结果上限
- **And** V1 对 `HIGH` 风险查询一律以 `APPROVAL_REQUIRED` fail closed 拒绝，不签发可执行计划，也不静默执行；当前没有人工批准路径

依据：报告 §10（statement timeout / row cap / byte cap、风险级别）、§14 Integration（EXPLAIN、timeout、row/byte cap）。

## AS-07 Lead→Reviewer 分析主链（Lead-to-reviewer analysis flow）

- **Given** 用户提出一个需要多步分析的问题
- **When** 运行分析
- **Then** 按顺序完成：Lead 澄清范围/时间/指标 → Metric Service 解析指标口径 → SQL Analyst 生成候选查询 → Query Policy 确定性验证 → EXPLAIN + 只读执行 → 脱敏限量结果写入 sandbox artifact → Data Analyst 统计分析与制图 → Reviewer 在全部 evidence 就绪后复核数字、口径与证据引用 → Report Writer 生成报告 → Lead 返回摘要、证据、风险与下载链接
- **And** 每个阶段的产物可作为证据被 Reviewer 引用；Reviewer 核对数字与 Evidence 引用的一致性
- **And** 子 Agent 不得再创建子 Agent；数据库查询默认串行

依据：报告 §7（运行数据流）、§8（Agent 责任与禁止能力）、§14 Workflow。

现行状态边界：当前只有 `business-analysis` skill 提示 Lead 使用 `general-purpose` 子 Agent 扮演 Data Analyst 与 Reviewer；没有专职 SQL Analyst、Reviewer 或 Report Writer。该主链仍是目标验收，不是已实现的多专职 Agent 产品行为。

## AS-08 子 Agent 失败恢复（failed subagent recovery）

- **Given** 分析流程中某个子 Agent 失败、超时、被取消，或触发 loop detection / token budget
- **When** 该故障发生
- **Then** 运行不崩溃且不静默成功：故障被记录为结构化 run event 与 receipt，主流程按既定策略继续，或以明确的失败结束并说明原因
- **And** Reviewer 拒绝结论时只允许有限重试；重试次数用尽后如实报告未通过的结论，不伪造通过
- **And** token 消耗与耗时被正确汇总到 receipt；取消与超时能终止底层执行

依据：报告 §4 KEEP（Subagent executor 隔离 event loop、超时、取消、token 汇总、receipt）、§8（每类 Agent 分别配置 max turns/timeout/token budget）、§14 Workflow。

## AS-09 结构化 SSE 轨迹且无思维链（structured SSE trace without chain-of-thought）

- **Given** 一次正在运行的分析
- **When** 前端订阅 SSE 运行事件
- **Then** 事件以结构化形式展示：分析计划与当前阶段、Agent 生命周期与工具调用状态、SQL validation/risk/EXPLAIN/耗时/行数、artifact 与 evidence 引用、Reviewer 结论，以及 token/timeout/loop 等运行信息
- **And** 事件流中不包含模型 chain-of-thought 原文
- **And** 前端仅依据这些结构化事件渲染右侧轨迹面板

依据：报告 §7（每阶段发出结构化 run event，前端不展示 chain-of-thought）、§12（右侧轨迹面板内容）。

## AS-10 报告 artifact（report artifact）

- **Given** 一次已完成且通过 Reviewer 复核的分析
- **When** 用户请求产出报告
- **Then** 生成报告 artifact，并在 `analysis_reports` 中登记 thread/run/artifact 标识、标题、状态、evidence summary 与创建时间
- **And** 报告中的每个数字可回溯到 evidence 引用，不存在无证据来源的结论
- **And** artifact 可从 Web 下载；简单结果由 Lead 直接格式化，只有长报告使用 Report Writer

依据：报告 §7、§8（Report Writer 能力边界）、§11（`analysis_reports`）、§14 E2E（下载报告）。

现行状态边界：`publish_analysis_report` 只登记报告索引 metadata，不读取或校验 artifact 内容及其数字/evidence 对应关系。文件写入与 `present_files` 由 skill 指导 Lead 单独执行；完整链尚未真实端到端验收。

## AS-11 计划分析（scheduled analysis）

- **Given** 已配置一个计划任务且 Scheduler 处于启用状态
- **When** 到达触发时间
- **Then** Scheduler 触发一次非交互分析运行并生成 artifact
- **And** 该运行不依赖用户在线，不阻塞等待人工澄清
- **And** 并发与排队行为符合配置的运行上限，不静默跳过重叠运行

依据：报告 §4 KEEP（Scheduler）、§14 E2E（Scheduler 触发分析并生成 artifact）、§17 Recommended 范围。

现行状态边界：Scheduler 已有通用非交互 Gateway run、持久队列与并发控制，但没有真实业务分析 artifact 链验收；不得把通用 Scheduler run 等同于已完成计划分析。

## AS-12 PostgreSQL 重启恢复（PostgreSQL restart recovery）

- **Given** 运维已显式把应用 `database.backend` 配置为外部 PostgreSQL，并在其中持久化 thread、run、run_events、checkpoint 与 artifact 元数据
- **When** Gateway 与 PostgreSQL 重启完成后
- **Then** thread 与 run 历史可恢复并在前端继续查看
- **And** 可从持久化 checkpoint 继续，已产生的 evidence 与 artifact 记录不丢失
- **And** 重启过程中未完成的运行状态在恢复后如实反映，不被伪装为成功

依据：报告 §4 KEEP（可选 PostgreSQL persistence/checkpoint）、§14 E2E（PostgreSQL 持久化后重启恢复 thread/run）、§15（应用 PostgreSQL 为显式外部配置，不属于默认 Compose）。

现行状态边界：默认应用数据库是 SQLite；可选 PostgreSQL 后端的 Gateway/PostgreSQL 重启恢复尚未完整实测验收。

## AS-13 平台结构化 Analytics 输出边界（structured Analytics output boundary）

- **Given** 数据源凭据仅通过环境变量或 secret file/provider 注入，数据库仅保存 `secret_ref` 而不保存明文密码；列标记为 sensitive/PII
- **When** 认证用户请求包含该 HIGH 列的查询
- **Then** V1 以 `APPROVAL_REQUIRED` fail closed 拒绝；不签发可执行 query plan ID、不执行任何业务数据库查询、不返回结果行
- **And** 平台生成的结构化 Analytics metadata、审计与对外/持久化运行事件投影不得包含原始 SQL、一次性 plan token、数据源凭据或原始结果行；允许保留稳定决定码、已定义的安全 evidence、计数与状态
- **And** 该保证只覆盖平台生成的结构化字段；任意用户/模型文本、模型最终回复和 artifact 正文不保证绝无敏感内容，本契约不要求扫描或改写其自由文本
- **And** 可选第三方 tracing 可能独立采集 prompt、tool input/output 与 completion；运维必须关闭该 tracing，或另行控制受信目标、访问权限和保留期。该外部导出不由本切片的结构化投影测试证明
- **And** 标记为 sensitive/PII 的列在 V1 不支持“获批后查询”或动态结果脱敏；动态 PII 脱敏尚未实现，不得宣称已具备

依据：报告 §10（V1 HIGH 拒绝策略）、§11（`secret_ref` 禁止明文、审计禁止保存敏感结果行）、§14 Security（拒绝路径的安全 metadata 边界）。Phase 6E3A 为部分运行输出路径加入结构化投影；整项 AS-13 仍须按证据矩阵完成 GPT 复验与后续真实验收。

## AS-14 受控分析工具边界与 MCP 保证范围（Controlled analysis boundary and MCP scope）

- **Given** 平台托管的 Analytics 数据源
- **When** 通过平台 `query_business_data` 路径访问
- **Then** 查询必须经过平台 Query Policy、授权、限额、超时与审计闭环；该保证属于平台 Analytics 工具，不推及任意第三方 MCP
- **And Given** 普通聊天启用了操作者配置的第三方 MCP
- **Then** 普通聊天保留这些已配置工具；产品不承诺它们遵循平台 SQL Query Policy 或同等审计
- **And Given** 一个受控分析运行
- **Then** 模型工具 schema 与最终执行分发必须来自同一固定正向集合，且精确限于 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`
- **And** `write_analysis_report` 只能由 Gateway 为已准入的分析 run 绑定的 server-owned capability 调用；它只写受控 Markdown artifact 并登记成功回执，不提供通用文件系统访问、HTML 执行或不受限直链
- **And** 普通/durable MCP、bash/命令执行、任意文件工具、动态插件、`tool_search`、`task`/子 Agent、`publish_analysis_report` 与未知新工具均不可见且不可执行
- **And** MCP 热更新、延迟发现和历史或伪造 `tool_call` 不得扩大该集合
- **And** 首次分析消息先以同一 UUID 持久创建 `kind=analysis`；analysis 专属 SDK thread-create 请求仍携带该 kind，thread-scoped stream 必须使用同一 UUID；普通聊天请求形状不变
- **And** 未认证/default 用户、不同所有者或普通线程、缺失/损坏标记、Analytics 服务不可用、writer capability 无法签发时必须 fail closed，不能降级为普通 Lead 图

依据：已批准的 [Phase 6E2B 运行隔离边界](../prompts/phase-06e2b-controlled-analysis-runtime.md) 与 6E2B1 工具 allowlist 切片。本场景区分平台 Analytics 的 Query Policy 保证和普通聊天 operator MCP 的权限范围。

现行状态：6E2B2B 已接通受控入口。Gateway 只接受持久化分析标记、受信用户、仍绑定的 Analytics services 与成功签发的 run-scoped writer；任何条件不成立都保持 `analysis_mode_unavailable`。定点合成 Gateway 生命周期测试使用 fake model 与合成数据，验证真实 Gateway admission→catalog/query/writer→artifact GET，并验证跨线程 artifact GET 为 404；定点前端 Playwright 证明自定义预创建与 SDK thread-create 的 kind/UUID 相同、stream URL 使用同一 UUID、冲突不启动流且普通聊天不进入分析页。真实 PostgreSQL/MySQL、真实模型与 Compose 用户验收仍未执行，故 AS-14 仍是发布阻塞，本切片不等于最终验收。

## AS-15 四服务默认 Compose 启动（four-service default Compose startup）

- **Given** 一份按默认配置准备的单机运行环境（`config.yaml` 与 secret 注入就绪）
- **When** 执行默认 Compose 启动
- **Then** 恰好启动四个默认服务：`nginx`、`frontend`、`gateway`、`redis`；生产 `make up` 仅在 Gateway readiness health 探针通过后报告启动成功
- **And** 从 nginx 统一入口可完成登录并进入分析工作台
- **And** Nginx 入口默认只绑定 `127.0.0.1`，Gateway 与 Redis 端口不发布到宿主机
- **And** 应用数据库默认为持久 SQLite（`backend/.deer-flow/data/deerflow.db`）；显式 PostgreSQL 应用数据库与业务 PostgreSQL/MySQL 均由运维作为外部依赖配置，不由默认 Compose 启动
- **And** Redis 是默认必需服务；AIO sandbox 仅通过显式 DooD overlay 启用
- **And** 冷启动路径不依赖任何已删除的 Provider/Provisioner 组件

依据：报告 §1（四个默认容器预算）、§15（当前默认 Compose 拓扑与外部数据库边界）、§14 E2E。

现行状态边界：2026-09-24 的本机记录验证了容器健康、入口 HTTP 路由和未登录保护，但没有创建管理员或完成认证后进入工作台；AS-01 的完整登录验收仍未完成。

---

## 场景与阶段对应

| 场景 | 主要验收阶段 |
| --- | --- |
| AS-01, AS-15 | 6 部署与验收 |
| AS-02, AS-03, AS-04, AS-05, AS-06, AS-13, AS-14 | 2 安全数据链 |
| AS-07, AS-08, AS-09 | 3 Agent 工作流 |
| AS-10, AS-11, AS-12 | 3 Agent 工作流 / 6 部署与验收 |
| AS-09, AS-10 | 4 前端工作台 |

## 更新规则

- 本文件是发布级契约，不因单个 Phase 的便利而放宽。
- 修改任一场景必须同时说明依据的架构报告章节；若与架构报告冲突，以架构报告为准并先提交 ADR。
- 新增场景必须来自已批准的架构报告范围，不得引入新的产品范围。
