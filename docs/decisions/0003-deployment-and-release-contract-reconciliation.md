# ADR 0003：按现行单机部署与已验证边界修订发布契约

- 状态：Accepted
- 日期：2026-09-24
- 决策人：Phase 6D1 架构与实施复核
- 修订：架构报告 §1/§2/§4/§10/§14/§15/§17、ADR 0001 部署预算及发布场景 AS-06、AS-07、AS-10–AS-15 的现行事实说明

## 背景

早期架构报告把 PostgreSQL 写成默认 Compose 服务，把 Redis 写成可选组件，并把专职 SQL Analyst、Reviewer、Report Writer、HIGH 人工批准、PII 结果脱敏与 MCP 统一策略描述为目标链路。现行代码与默认 Compose 并不完全兑现这些描述。继续把设计目标写成现有能力，会让部署、数据恢复和安全边界无法被复核。

本 ADR 只修订部署事实、发布契约和验收状态；不修改生产运行时，不移动 `upstream-v2.1.0-rc0`，不改写 Phase 5 文件预算目标。

## 已核实事实

1. `docker/docker-compose.yaml` 与 `docker/docker-compose-dev.yaml` 的默认服务均为 `nginx`、`frontend`、`gateway`、`redis`。Redis 在默认栈中启动并作为 StreamBridge 的 Redis Streams 后端；它不是可选 profile，也不发布宿主机端口。Gateway 默认一个 worker。
2. `config.example.yaml` 与 `backend/packages/harness/deerflow/config/database_config.py::DatabaseConfig` 将应用数据库默认设为 SQLite，目录为 `.deer-flow/data`，文件名为 `deerflow.db`。Gateway 在 `backend` 工作目录运行，因此默认文件位于 `backend/.deer-flow/data/deerflow.db`；Compose 将 `backend/.deer-flow` 持久挂载到 Gateway 容器。`database.backend: postgres` 可显式启用，但连接实例由运维提供，默认 Compose 不启动 PostgreSQL。
3. Analytics 登记的 PostgreSQL/MySQL 是独立业务数据源，经服务端 `secret_ref` 和只读账号访问；它们不等同于应用持久化数据库。
4. `business-analysis` skill 只规定顺序和证据纪律。它把 Data Analyst、Reviewer 角色交给内置 `general-purpose` 子 Agent；没有专职 SQL Analyst、Reviewer 或 Report Writer 定义。`query_business_data` 经受控服务完成计划与执行。
5. `publish_analysis_report` 写入报告索引 metadata，不打开、读取、复制或校验 artifact 内容。Skill 另行指示 Lead 使用 sandbox 写文件并用 `present_files` 交付；当前没有真实模型业务分析 artifact 链的端到端验收。
6. Scheduler 有通用非交互 Gateway run、持久队列、重叠排队与恢复能力，但未以真实业务分析 artifact 链完成端到端验收。
7. HIGH 风险（包括标记为 sensitive/PII 的列）在 V1 以 `APPROVAL_REQUIRED` fail closed 拒绝，不签发可执行计划、不执行业务查询、不返回结果行；V1 没有人工批准路径，也没有动态 PII 结果脱敏。安全结论是“拒绝并不向结果通道写入数据”，不是“已脱敏后允许访问”。
8. 默认应用数据库是 SQLite。PostgreSQL 应用数据库可选，但 Gateway/PostgreSQL 重启后的 thread、run、checkpoint、artifact 恢复尚无完整实测验收。
9. 平台自有 Analytics 工具走受控查询策略；任意第三方 MCP 工具由 Harness discovery/invocation 路径加载，未被强制接入 Analytics Query Policy。AS-14 仍是发布阻塞，不能用管理员配置约定证明通用安全保证。
10. 6C 后在 6D1 起点实测 tracked files 为 2251；加上本切片新增的两份文档后，tracked files 为 2253，850–1050 目标仍未达到。

## 决策

1. 默认 Docker Compose 保持简单单机路径，服务固定为 Nginx、Frontend、Gateway、Redis。仅 Nginx 的 `2026` 端口对宿主机发布，默认 loopback；Gateway `8001` 与 Redis `6379` 保持 Compose 网络内部。
2. 应用数据库默认 SQLite，使用 `backend/.deer-flow/data/deerflow.db` 持久化。选择 PostgreSQL 作为应用数据库属于显式运维配置，且需由外部实例提供；不为满足旧文档把 PostgreSQL 加入默认 Compose。业务 PostgreSQL/MySQL 继续作为外部数据源。
3. 修订架构报告与 ADR 0001 的部署预算条目：预算仍是四个默认容器，但服务组成是 `nginx`、`frontend`、`gateway`、`redis`；Redis 不是可选容器，应用 PostgreSQL 不是默认容器。
4. `docs/acceptance/phase-06d-contract-reconciliation.md` 是 AS-01..AS-15 的现行证据矩阵。矩阵状态只表示当前证据：代码/自动测试已证实、仅设计/尚未真实验收、与现行实现矛盾。端到端链路未验证的部分继续作为验收缺口，不因单元测试通过而标为已验收。
5. 对 HIGH/PII 保留 fail-closed 安全要求并精确写为 V1 拒绝路径；不引入动态脱敏或审批的虚假承诺。专职分析角色、完整 Scheduler artifact 链、PostgreSQL 重启恢复均保留为未验收目标。
6. AS-14 保留为发布阻塞。此阻塞要求未来限制或统一仲裁可访问业务数据的 MCP 路径；它不阻止 6D2 只验证平台自有受控 Analytics 查询路径，也不授权对任意 MCP 作安全承诺。
7. Phase 5 仍为进行中；tracked file 目标 850–1050 不变，不能为达标删除安全测试或把 B1–B5 完成表述为 Phase 5/发布完成。

## 取舍

| 方案 | 决定 | 原因 |
| --- | --- | --- |
| 把 PostgreSQL 加入默认 Compose，恢复早期报告写法 | 否决 | 当前单机默认已用 SQLite 持久化；额外数据库服务增加内存、磁盘、初始化、备份与健康检查成本，且没有证据表明默认试用需要该成本。 |
| 把 Redis 移出默认栈或改成可选 profile | 否决 | 两个默认 Compose 文件都依赖 Redis Streams；声称可选会与实际默认配置和健康依赖冲突。 |
| 把当前目标 Agent 流程、Scheduler 或 artifact 链写成已验收 | 否决 | skill 指令、mock、元数据索引和通用 run 测试不能代替真实 Agent→受控查询→artifact→复核链。 |
| 以配置约定代替 MCP 强制安全边界 | 否决 | 任意 MCP 服务能提供独立工具；管理员“不配置危险 MCP”不能证明系统级统一授权、限额、脱敏和审计。 |
| 现在添加审批、专职 Agent、动态 PII 脱敏或全局 MCP 策略运行时代码 | 不在本切片 | 6D1 是承诺与事实对账；实现新的安全机制需要单独设计、代码和回归验收。当前 AS-14 风险已明确为发布阻塞。 |

## 成本与影响

- SQLite 保持默认部署轻量并可持久化，但它是单机默认；多 Gateway worker 或需要共享应用存储时，运维需显式配置 PostgreSQL 并接受独立部署、连接凭据、迁移、备份和运维成本。
- Redis 是默认 Compose 的第四个容器，带来独立数据卷和健康依赖；本机 `make dev` 的单进程默认仍可使用 memory StreamBridge。
- 业务数据库不会随默认栈启动；使用者须自行准备 PostgreSQL/MySQL、合成或批准的数据和只读账号。
- AS-14 限制产品的通用安全发布声明。平台只能对内置 Analytics 查询路径声明当前代码与测试覆盖，不能把任意第三方 MCP 包含在同一策略保证内。
- HIGH/PII 被拒绝意味着当前 V1 不提供获批后访问敏感列或动态脱敏；测试只证明拒绝路径、无业务查询和安全 metadata，不证明可脱敏访问。
- 6D1 文档新增两份文件，tracked 数量由起点 2251 增至 2253；850–1050 目标未达成，需在 Phase 5 后续预算复核中处理。

## 重评估触发器

- 用户或部署证据显示默认 SQLite 在目标工作负载、并发、可用性或恢复目标下不足，或多 Gateway worker 成为受支持默认。
- PostgreSQL 应用存储完成迁移、故障注入、重启恢复与备份恢复的端到端验收，并确认将其作为默认服务能降低而非增加部署风险。
- 新的跨 MCP 数据访问仲裁层覆盖所有可提供业务数据访问的工具，并有针对性绕过测试和同等审计证据；在此之前 AS-14 不解除阻塞。
- 产品实现并验收了明确的 HIGH 人工批准、数据最小化/动态 PII 脱敏，以及专职分析角色或有界 Scheduler artifact 闭环；届时据此更新场景，不提前认领。
- Phase 5 对剩余代码、测试与预算完成新的基线审计；未满足此触发条件前，不改写 850–1050 的原目标。

## 参考

- [架构重构报告](../architecture/architecture-refactoring-report.md)
- [ADR 0001](0001-insightflow-hard-fork.md)
- [发布级验收场景](../acceptance/acceptance-scenarios.md)
- [Phase 6D1 证据矩阵](../acceptance/phase-06d-contract-reconciliation.md)
- [本机试用指南](../LOCAL_TRIAL.md)
