# InsightFlow 架构重构报告

> 基线：ByteDance DeerFlow `v2.1.0-rc0`
>
> 上游提交：`769589e8daee14c2587a634b6b43bd96471a41a1`
>
> 本地基线标签：`upstream-v2.1.0-rc0`
>
> 决策路线：A——保留 Agent Harness，垂直领域化硬分叉
>
> 日期：2026-09-21

## 1. 执行摘要与规模预算

InsightFlow 是面向企业经营分析的 Autonomous Data Analyst，不是通用 Agent 平台，也不是 DeerFlow 的换皮版本。产品主链必须完整覆盖“业务问题 → 指标口径 → 安全查询 → 数据分析 → 证据复核 → 报告交付”。

规模采用预算而非单一文件数考核：

| 指标 | 上游基线 | 推荐目标 | 硬上限/说明 |
| --- | ---: | ---: | --- |
| Git tracked files | 2917 | 850–1050 | 1200；不为达标删除必要安全测试 |
| 生产源码文件 | 约 1300 | 450–650 | 不含测试、迁移、生成物和 lockfile |
| 测试文件 | 约 1020 | 250–350 | 重点保留运行时、SQL 安全和关键 E2E |
| 有效文本代码行 | 约 82 万 | 14–22 万 | 排除 lockfile、生成物和大型 fixture |
| 默认容器 | 4+可选组件 | 4 | nginx、frontend、gateway、redis |
| 可选 Compose 服务/overlay | 多类 Provider/Provisioner | 默认 0 | AIO sandbox 通过显式 DooD overlay；应用 PostgreSQL 由运维提供，不属于默认 Compose |

低于约 650 个 tracked files 的“极简版”需要进一步移除 Scheduler、MCP、Memory 或大量运行时测试，不符合当前企业级目标。推荐以 850–1050 个文件为收敛区间，以模块职责、默认部署复杂度和安全证据作为更高优先级指标。

## 2. 基线清单

上游 tag 共 2917 个 tracked files，主要分布为：

| 区域 | 文件数 | 判断 |
| --- | ---: | --- |
| `backend/` | 1627 | 核心改造区；其中 tests 767、packages 618、app 121 |
| `frontend/` | 913 | 大幅收缩为分析工作台 |
| `skills/` | 104 | 仅保留分析、图表、报告类能力 |
| `docs/` | 95 | 删除上游产品文档，保留项目决策和运维文档 |
| `scripts/` | 45 | 删除 Provider/Skill 市场相关脚本 |
| `deploy/` + `docker/` | 47 | 收敛为 Compose 主路径 |
| `.github/` | 23 | 改造成 InsightFlow 的精简 CI |

当前 Gateway 内嵌 LangGraph runtime，主执行路径是 `RunManager + run_agent() + StreamBridge`，不是两个独立后端服务。生产与开发 Compose 默认包含 Nginx、Frontend、Gateway、Redis 四个服务；应用数据库默认是 SQLite（`backend/.deer-flow/data/deerflow.db`），可显式配置外部 PostgreSQL。业务 PostgreSQL/MySQL 是独立外部数据源，不是默认栈服务。

## 3. 产品边界

### 3.1 目标用户

- 企业经营、区域、销售和运营负责人。
- 能理解业务指标但不要求编写 SQL 的数据使用者。
- 配置数据源、指标和访问策略的管理员。

### 3.2 核心问题

- 用自然语言提出经营问题。
- 在明确的数据权限和指标口径下生成可审计 SQL。
- 对结果进行统计分析、可视化和交叉复核。
- 产出带证据链的结论和报告。

### 3.3 V1 非目标

- 通用 Agent/Skill 市场。
- IM 机器人平台。
- RAG 文档知识库；该能力由 Ragent 承担。
- 浏览器自动化平台。
- 多媒体生成平台。
- Kubernetes、多租户 SaaS 计费和复杂组织架构。

## 4. KEEP / MODIFY / DELETE 决策

### KEEP

- LangGraph Lead Agent、graph runtime 和现有流式运行模型。
- Gateway 的 Auth、Thread、Run、SSE、Artifact、Upload 主链。
- SQLite 单机默认持久化，以及可显式配置的 PostgreSQL persistence/checkpoint。
- Subagent executor、隔离 event loop、超时、取消、token 汇总和 receipt。
- Local Sandbox 与 AIO Docker Sandbox。
- Skill loader、activation、projection 和 policy。
- MCP 的基础 discovery、session 和 invocation。
- Scheduler、guardrail、loop detection、token budget、audit、receipt。
- `present_files`、`ask_clarification`、任务调度和基础 sandbox tools。

### MODIFY

- Lead Agent：从通用研究助手调整为业务分析编排器。
- Subagent registry：由 App 注册固定领域 Agent，不保留用户管理平台。
- Model factory：收敛到 OpenAI-compatible 与 DeepSeek 主路径。
- Memory：只保存用户业务偏好；保留 DeerMem/Noop。
- Skills：只保留数据分析、咨询分析、图表和报告相关能力。
- Gateway：增加 datasource、metric、report、query audit API。
- Frontend：改造成 InsightFlow 分析工作台和结构化执行轨迹。
- Compose：默认服务为 Nginx、Frontend、Gateway、Redis；SQLite 是默认应用存储，应用 PostgreSQL 由运维显式配置，AIO sandbox 使用 opt-in DooD overlay。
- MCP：目标架构要求平台业务数据访问 adapter 共用 Query Policy；现行可信分析仅准入固定 Analytics 工具，普通聊天 operator MCP 独立于该策略保证。AS-14 已按 [6F2批准边界](../acceptance/phase-06f2-as14-boundary-evidence.md)验收，不要求统一治理任意第三方 MCP。

### DELETE

- Channels、IM integrations、相关 OAuth/Webhook。
- ACP、durable `batch_task`、subagent batch UI/API。
- Managed/Custom Agent 管理平台。
- Skill marketplace/evolution/creator/reviewer/find。
- Browser 自动化及其 UI。
- Projects/Documents/Trash 通用产品模块。
- Voice、Docs、Blog、Showcase、GitHub Stars 和营销 Demo。
- E2B、BoxLite、OpenSandbox、Tenki、Kubernetes provisioner。
- Honcho、Mem0、OpenViking。
- 专属 Claude/Codex/MindIE/MiMo/MiniMax/StepFun/vLLM adapter。
- 图片、音乐、视频、播客、PPT 等媒体 Skills。

## 5. 删除影响与顺序

静态影响扫描得到的关联文件规模不是可直接删除数量：

| 能力 | 关联文件约数 | 主要耦合 |
| --- | ---: | --- |
| Channels | 124 | app 生命周期、router、config、persistence、前端、Docker env |
| Managed/Custom Agents | 93 | router、service、config、DB、前端设置、测试 |
| Projects/Trash | 60 | router、documents、tools、DB、前端、browser |
| Subagent Batch | 54 | harness、app、frontend、tests、config |
| Skill 平台 | 54 | API、审查脚本、CI、前端、公开 Skills |
| ACP | 47 | runtime、models、API、依赖、测试 |
| Browser | 40 | Gateway、project docs、前端 side panel、Playwright |

删除必须遵循：先建立替代主链和契约测试，再解除 router/config/生命周期引用，然后删除实现和依赖，最后清理测试与文档。不得以目录级批量删除代替依赖分析。

## 6. 目标总体架构

```text
InsightFlow Web
  │ REST + SSE
  ▼
Gateway / Auth / Thread / Run / Artifact
  │
  ▼
backend/app/analytics
  ├─ domain          纯业务模型和策略
  ├─ application     用例、端口和事务边界
  ├─ infrastructure  SQLAlchemy、SQLGlot、DB adapters、repositories
  ├─ agent           领域 tools、Agent 定义、prompt
  └─ api             FastAPI routers 和 schemas
  │
  ▼
DeerFlow Harness
  ├─ Lead runtime / LangGraph
  ├─ middleware chain
  ├─ subagent execution
  ├─ sandbox / skills / MCP
  └─ checkpoint / receipts / guardrails
```

依赖规则：

```text
app → harness
harness ✗→ app
domain ✗→ FastAPI / LangChain / SQLAlchemy
agent tools → application ports
infrastructure → domain/application ports
```

App 通过 composition root 向 Harness 注册领域 tools 和不可变的 subagent definitions。Harness 只提供通用注册接口，不硬编码 InsightFlow 业务 Agent，也不反向 import App。

## 7. 运行数据流

```text
用户问题
  → Lead 澄清范围/时间/指标
  → Metric Service 解析指标口径
  → SQL Analyst 生成候选查询
  → Query Policy Service 确定性验证
  → EXPLAIN + read-only executor
  → 脱敏、限量结果写入 sandbox artifact
  → Data Analyst 分析/制图
  → Reviewer 核对数字、口径和证据引用
  → Report Writer 生成报告 artifact
  → Lead 返回摘要、证据、风险和下载链接
```

每个阶段发出结构化 run event，前端只展示计划、工具状态、SQL 风险、耗时、数据行数、artifact 和审查结论，不展示 chain-of-thought。

这是目标数据流，不是对当前运行状态的描述。普通聊天可由 Lead 通过 `task` 委派内置 `general-purpose` 子 Agent，并按 skill 提示扮演角色；可信分析当前关闭 task、Skills、Memory和通用计划模式，仅使用 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`。Gateway run-scoped writer与绑定本次Lead模型的有界零工具Reviewer已实现，窄范围真实PostgreSQL查询/evidence/报告发布及历史轨迹已有证据；专职五角色链和完整端到端验收仍未完成，详见 [Phase 6D1 证据矩阵](../acceptance/phase-06d-contract-reconciliation.md)与[当前能力清单](../current-capabilities.md)。

## 8. Agent 架构

| Agent | 责任 | 允许能力 | 禁止能力 |
| --- | --- | --- | --- |
| Lead | 澄清、计划、委派、汇总 | metric lookup、task、artifact、clarification | 任意 SQL/凭据访问 |
| SQL Analyst | Schema 探索、候选 SQL | datasource/schema/metric/query 工具 | bash、任意网络、明文密码 |
| Data Analyst | 统计、异常、图表 | 已导出文件、Python sandbox、分析 skills | 直接访问业务数据库 |
| Reviewer | 数字/口径/证据复核 | evidence bundle、receipt、只读元数据 | 默认不重新查询数据库 |
| Report Writer | 结构化报告 | 已批准 findings、artifact write | 数据库和外部网络 |

以上Lead、SQL Analyst、Data Analyst、Reviewer、Report Writer角色表是目标设计，Metric Service是服务而非Agent。现行没有完整专职角色链：普通聊天支持通用task角色扮演，可信分析不走此路径。报告写入/发布能力已由Gateway按run签发，发布前Reviewer采用同模型、有界、零工具的复核能力；这不等于专职Reviewer或Report Writer子Agent已实现。

约束：

- 子 Agent 不得再次创建子 Agent。
- 数据库查询默认串行；数据文件分析可按任务有限并发。
- Reviewer 必须在全部 evidence 就绪后运行。
- 简单结果由 Lead 格式化；只有长报告使用 Report Writer。
- 每类 Agent 分别配置 max turns、timeout 和 token budget。
- 保留 SubagentExecutor 的执行 ID、轮询、取消和 receipt 能力。

## 9. Tool 与 MCP 架构

面向 LLM 暴露少量粗粒度、安全工具：

- `list_datasources`
- `get_datasource_schema`
- `get_metric_definition`
- `prepare_query`
- `execute_readonly_query`
- `export_query_result`
- `record_analysis_evidence`
- `save_report_metadata`

`prepare_query` 在内部完成解析、权限、LIMIT 和 EXPLAIN；`execute_readonly_query` 只能接收前一步签发的短期 query plan ID，不能直接接收任意 SQL。数据库凭据只存在于服务端 secret provider。

MCP 保留为扩展机制，可提供外部指标目录或企业系统 connector。目标中的平台 MCP datasource adapter 必须调用相同的 Query Policy 契约，核心数据访问不能只实现为 MCP。现行可信分析以固定三工具集合与Gateway fail-closed准入约束；普通聊天的operator MCP可执行其自身操作，不受平台Query Policy保证。AS-14已按[6F2批准边界](../acceptance/phase-06f2-as14-boundary-evidence.md)验收，universal MCP mediation不是现行发布要求，不据此承诺任意第三方MCP安全。

## 10. Text2SQL 安全设计

```text
候选 SQL
  → 显式 dialect 解析
  → 单语句和允许 AST 根节点
  → DDL/DML/Command/事务/导出黑名单
  → datasource/schema/table/column 白名单
  → PII 和聚合策略
  → AST 级 LIMIT 注入或收紧
  → 同方言序列化并重新解析
  → EXPLAIN 成本和扫描量判断
  → 数据库只读事务执行
  → statement timeout / row cap / byte cap
  → 结果安全规范化（不代表已实现动态 PII 脱敏）
  → audit + evidence receipt
```

SQLGlot 只承担 parser/AST/transpiler，不被当作安全验证器。任何解析为通用 `Command`、无法解析、方言不确定、包含多语句或未知实体的输入均 fail closed。

风险级别：

- `LOW`：白名单表列、低成本、有界 SELECT。
- `MEDIUM`：复杂 JOIN、较大时间范围或较高但可接受成本；使用更低超时和结果上限。
- `HIGH`：敏感/PII 列、跨 schema、笛卡尔风险或高成本；V1 当前一律以 `APPROVAL_REQUIRED` fail closed 拒绝，没有人工批准路径，不签发可执行计划且不执行查询。
- `BLOCKED`：写操作、DDL、事务控制、多语句、权限越界、解析歧义、文件/网络导出。

防御纵深包括独立只读数据库用户、只读事务、连接池上限、服务端超时、结果截断和审计，不能只依赖 AST。

当前 V1 的敏感/PII 边界是 HIGH fail-closed 拒绝与不返回结果行，不能描述为“动态脱敏后允许查询”。

## 11. 数据模型

优先复用现有 users、threads、runs、run_events、scheduled_tasks 和 artifacts 语义，新增：

### `datasources`

- `id`, `owner_id/tenant_id`, `name`, `engine`
- `secret_ref`，禁止保存明文密码
- `default_schema`, `policy_config`, `status`
- `created_at`, `updated_at`

### `datasource_permissions`

- `datasource_id`, `principal_type`, `principal_id`
- schema/table/column allowlists
- row-policy reference 与 PII policy

### `metric_definitions`

- `key`, `name`, `description`, `expression/template`
- dimensions、owner、version、status

### `sql_query_audits`

- user/run/agent/datasource 标识
- query hash 与脱敏后的 SQL
- dialect、risk level、decision reasons
- EXPLAIN 摘要、row count、latency、outcome/error class
- 禁止保存敏感结果行

### `analysis_reports`

- thread/run/artifact 标识
- title、status、evidence summary、created_at

第一阶段不重写上游历史 migration；通过 forward migrations 新增表。删除的旧模块可以停止注册，但历史表迁移保留到首次稳定发布之后。

## 12. 前端信息架构

```text
/workspace/analysis/new
/workspace/analysis/[thread_id]
/workspace/datasources
/workspace/metrics
/workspace/reports
/workspace/scheduled-tasks
/workspace/history
/workspace/settings
```

复用现有 chat streaming、artifact panel、todo/task card 和 resizable layout。右侧轨迹面板展示：

- 分析计划与当前阶段。
- Agent 生命周期和工具调用状态。
- SQL validation、risk、EXPLAIN、耗时和行数。
- Artifact 和 evidence 引用。
- Reviewer 结论、token/timeout/loop 等运行信息。

删除 public docs/blog/showcase/github-stars、custom agent、projects/trash、channels、browser、voice 路由。Landing 重写为简洁的企业经营分析产品页。

## 13. 依赖清理

### 默认保留

- FastAPI、LangGraph/LangChain core、SQLAlchemy、asyncpg。
- `langchain-openai`、`langchain-deepseek`。
- SQLGlot、MySQL async driver、Pydantic、Alembic。
- Next.js/React、SSE 客户端和现有基础 UI 组件。
- Tavily 仅作为 Recommended 范围的可选 web search/fetch。

### 候选删除

- Anthropic、Google GenAI 和专用模型 SDK。
- E2B、Kubernetes、ACP、OpenViking。
- 多套搜索/crawl/browser Provider。
- IM SDK、Nextra/营销内容相关包、voice/browser 前端依赖。
- Skill marketplace/reviewer 的评测与打包依赖。

每次删除依赖前先使用 import/reference scan 证明无活跃引用，并运行对应 package lock 校验、类型检查和最小启动测试。

## 14. 测试与质量门禁

### Unit

- SQL AST allow/deny、LIMIT、PII、risk classification。
- metric 解析、permission policy、secret redaction。
- Agent tool allowlist 和 middleware ordering。

### Integration

- PostgreSQL/MySQL 测试库的 read-only 查询。
- EXPLAIN、timeout、row/byte cap。
- repository/migration、Gateway API、scheduler、artifact。

### Workflow

- Lead → SQL Analyst → Data Analyst → Reviewer → Report Writer。
- 子 Agent 失败、取消、超时、loop/token budget。
- Reviewer 拒绝结论后的有限重试。

### Security

- DDL/DML、多语句、注释绕过、`Command` fallback。
- 越权 datasource/schema/table/column。
- 凭据和 PII 不进入日志、SSE、receipt、artifact。
- 平台Analytics数据访问必须经过Query Policy，可信分析工具集合与Gateway准入不得被绕过。普通聊天operator MCP在该保证范围外；AS-14按[6F2批准边界](../acceptance/phase-06f2-as14-boundary-evidence.md)已验收，不将任意第三方MCP统一治理作为现行门禁。

### E2E

- 登录 → 配置 datasource → 提问 → 查看轨迹 → 下载报告。
- Scheduler 触发分析并生成 artifact。
- PostgreSQL 持久化后重启恢复 thread/run。

每个阶段必须提交测试命令、退出码和关键输出，不接受只写“测试通过”。
本节列出目标门禁，并非整套工作流已运行通过。现行默认使用 SQLite；可选 PostgreSQL 应用后端的重启恢复尚无完整实测，真实自然语言业务分析 artifact 链也未验收。各场景的实现事实、自动测试和端到端边界见 [Phase 6D1 证据矩阵](../acceptance/phase-06d-contract-reconciliation.md)。

## 15. Docker 与运行环境

默认 Compose（生产与 Docker 开发）：

```text
nginx
frontend
gateway
redis
```

默认服务正好四个：`nginx`、`frontend`、`gateway`、`redis`。Redis 是默认必需服务，承载 Redis Streams bridge；它不发布宿主机端口。本地 `make dev` 的单进程默认可以使用 memory StreamBridge。

可选部署能力：

- 应用 PostgreSQL：在 `config.yaml -> database.backend: postgres` 显式配置，并由运维提供外部 PostgreSQL 实例；默认 Compose 不启动该实例。
- 业务 PostgreSQL/MySQL：管理员登记的外部业务数据源，不属于应用运行时数据库。
- AIO Docker sandbox：使用显式 DooD overlay，并按配置挂载 Docker socket。

约束：

- 默认 Compose 不包含 PostgreSQL，因此不会替运维发布应用数据库端口。配置外部 PostgreSQL 或业务数据源时，监听地址、TLS 与防火墙由运维明确设置。
- 业务 MySQL/PostgreSQL 不是 Compose 运行时数据库。
- datasource secret 通过环境变量或 secret file/provider 注入。
- image 使用固定 tag、非 root 用户、健康检查和结构化日志。
- Kubernetes/Helm 不进入 MVP。

## 16. 分阶段迁移计划

| 阶段 | 核心交付 | 主要文件区域 | 验收 | 回滚 |
| --- | --- | --- | --- | --- |
| 0 基线治理 | tag、架构文档、ADR、预算门禁 | root、`docs/`、CI scripts | tree hash、文档校验、基线命令 | 回到 `upstream-v2.1.0-rc0` |
| 1 领域骨架 | analytics 分层、ports、composition root | `backend/app/analytics/`、Gateway | import boundary tests、Gateway smoke | revert 单阶段提交 |
| 2 安全数据链 | datasource/metric/query policy/audit | analytics + migrations + routers | MySQL/PG integration、安全测试 | feature flag 关闭新 routers |
| 3 Agent 工作流 | 四类 Agent、工具矩阵、事件 | app agent + Harness registration | workflow/timeout/token/receipt | 切回原 Lead 配置 |
| 4 前端工作台 | 新 IA、轨迹、数据源/指标/报告 | `frontend/src/` | unit + Playwright 主路径 | feature route 回退 |
| 5 能力瘦身 | 删除旧平台与依赖 | backend/frontend/skills/config | reference scan、全套回归 | 按域独立 revert |
| 6 部署验收 | Compose、CI、E2E、运维文档 | docker/deploy/.github/docs | 冷启动、恢复、安全场景 | 使用上个可用镜像/tag |

每阶段只接受一个职责明确的主提交；必要修复使用后续小提交。禁止把所有删除和新功能压成一个不可审查提交。

## 17. 风险、低 ROI 项与范围分层

### 主要风险

| 风险 | 严重度 | 控制措施 |
| --- | --- | --- |
| 破坏 middleware 顺序 | 高 | 顺序快照测试；修改需 ADR |
| 删除模块仍被生命周期引用 | 高 | import/router/config 三层扫描 + startup smoke |
| LLM 绕过 SQL policy | 高 | query plan token；executor 不接收裸 SQL |
| MySQL/PostgreSQL 方言差异 | 高 | 显式 dialect + 双库集成 fixture |
| 日志/SSE 泄漏凭据或 PII | 高 | 统一 redaction + security tests |
| 大规模前端删除破坏共享组件 | 中 | 先路由替换，再删 core domain |
| 历史 migration 与删除模型冲突 | 中 | 保留历史，追加 forward migration |
| 为缩体量误删测试 | 中 | 覆盖矩阵优先于文件数预算 |

### 暂不投入的低 ROI 工作

- 全局重命名 `deerflow.*` Python namespace。
- 重写 LangGraph/Harness。
- 自研 SQL parser。
- 多租户计费、复杂 RBAC、Kubernetes operator。
- 同时支持大量模型和搜索 Provider。
- 把核心数据访问强行包装为 MCP。
- 为追求极小仓库删除安全回归和关键 upstream tests。

### 范围分层

**MVP**

- PostgreSQL runtime、MySQL/PostgreSQL datasource。
- Lead + SQL Analyst + Data Analyst + Reviewer。
- SQL 安全链、审计、Artifacts、SSE、Auth、History。
- 新建分析、数据源、指标中心、报告基础页。
- Compose 单机部署。

**Recommended**

- Report Writer、Scheduler、Tavily、MCP 基础扩展。
- AIO sandbox、结构化轨迹、图表报告。
- Redis StreamBridge 多 worker 配置（Redis 本身仍是默认 Compose 服务）。

**Optional**

- 企业 OIDC、更多 datasource adapter、远程指标平台 MCP。
- HIGH 风险人工批准工作流（当前 V1 未实现；在实现并验收前 HIGH 一律拒绝）。
- 多租户和 Kubernetes。

## 18. 项目学习与简历价值

该路线保留并强化以下可解释的工程主题：

- LangGraph 长流程编排与中间件顺序设计。
- 受约束的多 Agent 分工、隔离、取消和预算治理。
- SQL AST、权限、成本、只读执行和审计的安全闭环。
- 运行时数据库与异构业务数据源的端口/适配器设计。
- SSE、checkpoint、artifact、scheduler 和故障恢复。
- App/Harness 依赖倒置与大规模 OSS 二次开发取舍。
- 前后端结构化执行轨迹和可验证证据链。
- 基于风险的测试金字塔、Docker 交付和可回滚迁移。

最终项目的价值不在于保留 DeerFlow 的功能数量，而在于能解释“为何保留、为何删除、边界如何验证，以及一个自然语言问题如何安全地变成可信业务结论”。
