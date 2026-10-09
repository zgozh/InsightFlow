# InsightFlow AS-01～AS-15 完整发布验收计划

> 面向实施 Agent：按根 AGENTS 的“方案 → 实施与证据 → 主会话独立审查 → 下一切片”执行。用户最新指定 `gpt-6-luna` / max。每个切片有明确文件与环境所有权，不自行结束整体任务。

**目标：**兑现并完成现有 AS-01～AS-15 发布契约，保留已批准的安全范围和有效证据，不将简历演示或单个里程碑当成完整发布。

**架构：**保留 Gateway 内嵌 LangGraph 和 App/Harness 单向依赖。可信分析的外部模型工具 schema 和执行分发仍固定为三个 Analytics 工具；专职角色通过 App-owned、服务端固定且有界的内部执行链补齐，不能恢复普通 task、MCP 或任意文件/命令权限。查询继续经过现有确定性策略和只读执行边界。

**技术栈：**现有 Python/FastAPI/LangGraph/SQLGlot/SQLAlchemy，Next.js/React/TypeScript，默认 SQLite、外部 PostgreSQL、可选 MySQL、Redis 与 Compose；无预定新增运行依赖。

**契约与事实来源：**[发布场景](../../acceptance/acceptance-scenarios.md)、[批准 AS-14 范围](../../acceptance/phase-06f2-as14-boundary-evidence.md)、[本轮差距盘点](../../acceptance/2026-10-07-full-release-gap-audit.md)。历史 ADR 的旧 MCP 承诺不得覆盖后续批准范围。

## 全局约束与有效证据

- 不 push、不发布外部版本、不调整 release version；用户要求的是完整发布验收。
- 现有五容器固定栈、三卷、账号/会话和业务数据保留。新增验收项目和数据必须唯一标识、与原栈隔离；任何清理先核对标签和绝对路径。
- 6F3F21 首页源码与固定栈部署已独立复核；前端定点 checks、镜像 build、桌面/手机截图有效，不为新任务重复。
- 6F3F20 普通聊天工具→HTML预览已证实；交互变化未证实，且不再重复此示例。
- 验证级别 V3：用户明确选择全部发布验收。每个里程碑内部仍先做直接相关测试；仅在共享契约、安全、持久化和最终集成范围扩大时扩大验证。
- 6F2 的 AS-14 已验收范围保持；AS-13 只承诺平台结构化字段，不扩为任意用户/模型/artifact 自由文本保证。MySQL 流式 timeout 按客户端有界取消和连接销毁实证描述。

## 里程碑 1：真实多主体与默认四服务入口（AS-01、AS-15）

- [x] 确认认证、部署和临时数据隔离接缝：本轮差距盘点已完成；当前没有用户删除 API。
- [ ] 创建隔离的默认四服务 SQLite 验收栈，复用本轮已构建镜像；配置和应用 home 都在唯一忽略目录，不触碰原项目。
- [ ] 通过真实 initialize/register/login 建立 A/B 两主体；零模型，使用明确标为合成夹具的 thread/run/artifact/授权数据验证 HTTP 与 UI 边界。
- [ ] 证明未登录工作台跳转、API401无数据；B访问A的thread/run/messages/events/SSE/artifact拒绝，自身正常；非管理员不能调用管理员入口。
- [ ] 证明服务数、loopback、Gateway/Redis无发布、持久SQLite、readiness后才成功和真实登录进入分析工作台；保留隔离环境供后续验收，最终再精确清理。
- [ ] 运行直接相关 auth/owner、Compose bind/default服务与部署 readiness 定点检查，记录命令/退出码/安全摘要并由主会话独立复核。

本里程碑不修改生产安全契约；出现明确产品缺陷另写最小修复切片。交付文件 `docs/acceptance/2026-10-07-as01-as15-default-stack.md` 与状态矩阵/PROGRESS。临时 runner 归唯一 `.reviews` 子目录，不加入产品代码。

## 里程碑 2：受控领域角色与耐久 evidence（AS-07、AS-08、AS-09、AS-10、AS-12接口）

- [ ] 主会话根据差距报告冻结 App 内部角色、指标口径、结果 artifact/耐久 evidence、结构化阶段事件及数字引用契约，写对应 ADR 和实施提示词。内部角色不取得通用委派或直接数据库/任意文件能力。
- [ ] SQL Analyst 只产候选查询，所有查询经现有 policy/authorization/EXPLAIN/只读执行；Metric Service 用现有 MetricCatalog 的受权定义解析版本化口径；Data Analyst 只读同 owner/thread/run 的有界 evidence；Reviewer 和 Report Writer 分离职责并保持有限失败策略。
- [ ] 结果写固定受控 artifact并登记可恢复证据，报告的数字引用由确定性结构校验保护；不能只扫描全篇数字是否曾在任意结果出现，不能把模型 Reviewer 判定称为数学证明。
- [ ] 固定模型/返回值夹具保护阶段顺序、无二次委派、串行查询、超时/取消/预算/有限拒绝、数字错配、跨主体/跨run证据拒绝和持久恢复。
- [ ] 扩展前端纯结构化阶段投影，并做一个成功真实分析 live SSE/报告下载的里程碑验证。所有角色状态有真实执行记录，不能以标签冒充专职 Agent。

仅改 Analytics/Gateway受控能力、必要通用上下文键与前端trace契约的直接关联文件；具体文件/类型由主会话在实施前冻结，所有权串行。保持 `test_analysis_tool_allowlist.py` 的模型与 dispatcher 同一三工具不变量。高风险共享边界采用 V2/V3，安全/持久化回归先行。

## 里程碑 3：PostgreSQL 必验、MySQL 可选与风险分档（AS-02～AS-06、AS-13、AS-14复验）

- [ ] 实现并定点验证 MEDIUM 的更低 timeout/row/byte预算，上限只收紧；HIGH仍拒绝。保护配置解析、执行计划及delivery契约。
- [ ] PostgreSQL（AS-03）保留只读/方言/timeout/row/byte/迁移验收；AS-02 的 MySQL adapter/usecase 已有通过证据及本轮双库真实记录继续有效，不要求追加 MySQL 自然语言模型、HTTP 或事件验收。
- [ ] PostgreSQL 使用合成账本与自然语言问题跑受控真实模型链，以独立只读 SQL 作为数值 oracle；数字/evidence/report/run/owner一致。
- [ ] PostgreSQL 必验链路覆盖 HTTP 代表性越权、DDL/DML/事务/多语句/Unicode 注释绕过及 HIGH 拒绝不发业务执行；审计/结构化 SSE/history/checkpoint 输出不含 SQL、token、凭据、结果行。
- [ ] 主会话复验受影响安全投影与三工具准入，不扩大为第三方MCP或自由文本保证。

基础检查复用现有 `test_sql_policy.py`、`test_semantic_authorizer.py`、`test_analytics_delivery.py`、`test_result_normalizer.py`、PostgreSQL 集成和结构化投影相关文件；MySQL 已有 adapter/usecase 证据保留；修改面决定定点集合，最终 PostgreSQL 真实链不能被 mock 替代。

## 里程碑 4：计划分析与PostgreSQL应用库恢复（AS-11、AS-12）

- [ ] 在隔离应用PostgreSQL环境设置 `database.backend=postgres`、`database.postgres_url`、`run_events.backend=db`；应用库与业务库独立，默认栈不添数据库服务。
- [ ] 以 `context_mode=reuse_thread` 的持久analysis线程执行实际Scheduler非交互分析与报告；验证重叠durable queued、等待不占并发、无人工澄清。仅契约要求时补fresh analysis kind，不能未经需要扩大任务API。
- [ ] 保存成功/未完成run的安全标识及evidence/报告digest，重启隔离Gateway/PG；验证history/checkpoint/events/artifact/证据恢复和未完成状态不伪成功，再从checkpoint继续。
- [ ] 运行受影响Scheduler/PG persistence定点及必要真实故障注入，主会话复核。

复用 `test_gateway_services.py`、`test_scheduled_task_queue.py`、`test_scheduled_task_postgres.py`、`test_analytics_persistence_postgresql.py`；新证据持久化接口增加其真实恢复测试。

## 里程碑 5：完整集成与最终裁决（AS-01～AS-15）

- [ ] 逐条对照发布场景保留精确命令、退出码、关键输出、证据与限制；没有整条通过的场景保持未验收。
- [ ] 对最终影响面完成适用CI格式/静态/构建与集成检查；若发现既有/无关失败，按事实定位，不将失败写成PASS，也不自行扩大为无关清债。
- [ ] 独立审查最终diff、架构依赖、角色权限、数字证据、恢复边界和浏览器主流程；修复任务相关回归。
- [ ] 同步 README、模块AGENTS、acceptance矩阵、PROGRESS与简历能力清单；准确区分上游保留与二开贡献。
- [ ] 只有AS-01～AS-15均通过且无任务相关残差，才宣称发布验收完成。Phase5文件数量目标不因本计划完成而自动达标，不为数量删除安全测试。

## 阻塞处理

主机审批拒绝不绕过，缺必要凭据/权限或外部环境状态时明确记录并继续独立可行工作。只在用户显式暂停时暂停整体；阶段完成、旧记录说“停在复验”、状态询问或模型分工变更都不是停止整体任务的理由。
