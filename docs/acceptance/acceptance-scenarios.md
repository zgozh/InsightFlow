# InsightFlow 发布级验收场景

> 基线：DeerFlow `v2.1.0-rc0`（`upstream-v2.1.0-rc0`）
>
> 依据：[架构重构报告](../architecture/architecture-refactoring-report.md)
>
> 性质：发布级（release-level）验收契约。Phase 0 不交付运行时行为，因此本文件定义的是 Phase 1–6 必须满足的端到端验收口径，不随阶段重新解释。

每个场景在通过时必须提交：执行命令、退出码、关键输出与证据位置。只写「测试通过」不构成验收。

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
- **And** `HIGH` 风险查询在 V1 默认要求批准或拒绝，不静默执行

依据：报告 §10（statement timeout / row cap / byte cap、风险级别）、§14 Integration（EXPLAIN、timeout、row/byte cap）。

## AS-07 Lead→Reviewer 分析主链（Lead-to-reviewer analysis flow）

- **Given** 用户提出一个需要多步分析的问题
- **When** 运行分析
- **Then** 按顺序完成：Lead 澄清范围/时间/指标 → Metric Service 解析指标口径 → SQL Analyst 生成候选查询 → Query Policy 确定性验证 → EXPLAIN + 只读执行 → 脱敏限量结果写入 sandbox artifact → Data Analyst 统计分析与制图 → Reviewer 在全部 evidence 就绪后复核数字、口径与证据引用 → Report Writer 生成报告 → Lead 返回摘要、证据、风险与下载链接
- **And** 每个阶段的产物可作为证据被 Reviewer 引用；Reviewer 核对数字与 Evidence 引用的一致性
- **And** 子 Agent 不得再创建子 Agent；数据库查询默认串行

依据：报告 §7（运行数据流）、§8（Agent 责任与禁止能力）、§14 Workflow。

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

## AS-11 计划分析（scheduled analysis）

- **Given** 已配置一个计划任务且 Scheduler 处于启用状态
- **When** 到达触发时间
- **Then** Scheduler 触发一次非交互分析运行并生成 artifact
- **And** 该运行不依赖用户在线，不阻塞等待人工澄清
- **And** 并发与排队行为符合配置的运行上限，不静默跳过重叠运行

依据：报告 §4 KEEP（Scheduler）、§14 E2E（Scheduler 触发分析并生成 artifact）、§17 Recommended 范围。

## AS-12 PostgreSQL 重启恢复（PostgreSQL restart recovery）

- **Given** 一个已在 PostgreSQL 中持久化的 thread 及其 run、run_events、artifact 元数据
- **When** Gateway 与 PostgreSQL 重启完成后
- **Then** thread 与 run 历史可恢复并在前端继续查看
- **And** 可从持久化 checkpoint 继续，已产生的 evidence 与 artifact 记录不丢失
- **And** 重启过程中未完成的运行状态在恢复后如实反映，不被伪装为成功

依据：报告 §4 KEEP（PostgreSQL persistence/checkpoint）、§14 E2E（PostgreSQL 持久化后重启恢复 thread/run）、§15（postgres 为默认 Compose 必选组件）。

## AS-13 凭据与 PII 不进入日志和事件（secrets/PII absent from logs and events）

- **Given** 数据源凭据仅通过环境变量或 secret file/provider 注入，数据库仅保存 `secret_ref` 而不保存明文密码
- **When** 执行一次包含敏感列访问的完整分析
- **Then** 日志、SSE 事件、receipt、artifact 与 `sql_query_audits` 中均不出现明文凭据，也不出现原始 PII 结果行
- **And** 审计只保存 query hash 与脱敏后的 SQL，以及 EXPLAIN 摘要、row count、latency、outcome/error class
- **And** 结果按 PII policy 与聚合策略脱敏；以凭据/PII 样本扫描全部输出通道（日志、事件、receipt、artifact、审计表）的结果为空

依据：报告 §10（PII 与聚合策略、结果脱敏）、§11（`secret_ref` 禁止明文、审计禁止保存敏感结果行）、§14 Security（凭据和 PII 不进入日志、SSE、receipt、artifact）。

## AS-14 MCP 不能绕过查询策略（MCP cannot bypass query policy）

- **Given** 一个被配置为可提供数据访问的 MCP server
- **When** 通过 MCP 路径尝试访问任一数据源
- **Then** 该路径必须调用与本地路径相同的 Query Policy 契约；未通过策略的查询被拒绝，并产生与本地路径同等的审计记录
- **And** 不存在任何仅经由 MCP 绕过统一权限、LIMIT、超时、脱敏或审计的数据访问路径
- **And** 系统不把核心数据访问只实现为 MCP

依据：报告 §4 MODIFY（MCP 不能绕过统一查询安全层）、§9（MCP datasource adapter 也必须调用相同 Query Policy 契约）、§14 Security、§17（不把核心数据访问强行包装为 MCP）。

## AS-15 四服务默认 Compose 启动（four-service default Compose startup）

- **Given** 一份按默认配置准备的运行环境（`config.yaml` 与 secret 注入就绪）
- **When** 执行默认 Compose 启动
- **Then** 恰好启动四个默认服务：`nginx`、`frontend`、`gateway`、`postgres`，且仅在 gateway 通过 health 探针后才报告启动成功
- **And** 从 nginx 统一入口可完成登录并进入分析工作台
- **And** PostgreSQL 不暴露公网端口，开发环境仅绑定 localhost
- **And** `redis` 与 AIO sandbox 仅在显式启用 profile 时启动，默认不启动
- **And** 冷启动路径不依赖任何已删除的 Provider/Provisioner 组件

依据：报告 §1（默认容器 4）、§15（默认 Compose 与可选 profiles、PostgreSQL 端口约束）、§14 E2E。

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
