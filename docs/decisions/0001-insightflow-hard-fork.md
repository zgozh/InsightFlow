# ADR 0001：InsightFlow 采用「保留 Agent Harness 的垂直领域化硬分叉」路线

- Status: Accepted
- Date: 2026-09-21
- Decision maker: 项目架构评审（架构报告已批准）
- Supersedes: 无

## Context

InsightFlow 以 ByteDance DeerFlow `v2.1.0-rc0`（上游 commit `769589e8daee14c2587a634b6b43bd96471a41a1`，导入 tree `2473c22e163a3879490848a7995eb2b7be7f6f50`）为基线。该版本是一个体量很大的通用企业级 Agent 平台：基线共 2917 个 tracked files，其中 `backend/` 1627、`frontend/` 913、`skills/` 104。

同时项目有明确的产品与简历定位：做一个面向企业经营分析的 Autonomous Data Analyst，主链必须完整覆盖「业务问题 → 指标口径 → 安全查询 → 数据分析 → 证据复核 → 报告交付」，而不是通用 Agent 平台，也不是原项目的换皮。

由此产生的核心约束：

- 上游 Harness 的通用能力（LangGraph runtime、middleware chain、subagent 执行、sandbox、skills、MCP、checkpoint/receipts/guardrails）是真正的工程资产，值得保留并强化。
- 上游大量面向「通用平台」的能力（IM Channels、Agent/Skill 市场、浏览器自动化、多媒体生成、多 Provider 适配、Kubernetes provisioner 等）对本产品是纯负担。
- 体量必须收敛，但收敛的判据是模块职责、默认部署复杂度和安全证据，而不是单一文件数。
- 上游代码必须保持可追溯，二次开发范围必须可审计、可回滚。

## 评估过的三条路线

### 路线 A：保留 Agent Harness，垂直领域化硬分叉（采纳）

保留 LangGraph Lead Agent 与 graph runtime、subagent executor、sandbox、skill loader、MCP 基础能力、Scheduler/guardrail/audit/receipt 等通用底座；在其上新建 `backend/app/analytics` 业务域，把产品从「通用研究助手」改造成「企业经营分析」；其余无关能力按 Phase 分阶段删除。

### 路线 B：扩展优先覆盖（否决）

尽量保留上游全部能力，不删除横向产品外壳，而是通过 extension / plugin / skills 机制在其上增加 analytics 能力，并把旧 UI 隐藏起来。

- 优点：落地最快；改动面最小；最容易跟随上游版本演进。
- 缺点：仓库依然臃肿；容易退化成配置工程或换皮项目；无法满足体量预算与领域边界目标。
- 否决理由：与既定产品边界冲突——InsightFlow 不是通用 Agent 平台，也不是 DeerFlow 的换皮版本。以「隐藏」代替「删除」会让领域边界无法被验证，体量与默认部署复杂度目标也无法达成。

### 路线 C：运行时抽取/重写（否决）

从 Harness 中抽取少量所需能力到新项目，重建 App，不复用上游整体运行时。

- 优点：最终产物最小；架构边界最干净；不受上游历史包袱与既有结构约束。
- 缺点：工作量和回归风险最高；会丢失大量上游测试与二次开发价值。
- 否决理由：属于架构报告列出的「暂不投入的低 ROI 工作」（重写 LangGraph/Harness）。在项目周期内无法同时交付企业级安全链与完整回归证据，并放弃上游已验证的运行时资产。

> 说明：纯换皮（只改品牌与文案）与极端裁剪（把仓库压到约 650 个 tracked files 以下）属于本项目的非目标和规模警戒线，不是当时正式比较的架构备选。

## Decision

采纳路线 A：**保留 Agent Harness，垂直领域化硬分叉。**

具体决策内容：

1. **依赖方向固定为 `app → harness`。** Harness 不得反向 import App。App 通过 composition root 向 Harness 注册领域 tools 和不可变的 subagent definitions；Harness 只提供通用注册接口，不硬编码 InsightFlow 业务 Agent。

   相关的分层内聚规则：

   ```text
   app → harness
   harness ✗→ app
   domain ✗→ FastAPI / LangChain / SQLAlchemy
   agent tools → application ports
   infrastructure → domain/application ports
   ```

   `backend/app/analytics` 按 `domain` / `application` / `infrastructure` / `agent` / `api` 五层组织。

2. **不改名 `deerflow.*` Python namespace。** 全局重命名 namespace 被明确列为低 ROI 工作：改动面巨大、破坏与上游的可比对性、风险高而简历价值低。命名空间保持上游原样，产品身份通过 `UPSTREAM.md`、本项目新增的业务域与文档体现。

3. **基线不可变。** 首个提交的 tree 与上游完全一致，本地 tag `upstream-v2.1.0-rc0` 不得移动或重建；此后所有产品改动作为后续提交，`git diff upstream-v2.1.0-rc0..main` 即二次开发的可审计描述。

4. **保留 ByteDance/DeerFlow 署名。** 保留原 `LICENSE` 与适用版权声明（MIT）。

5. **规模按预算收敛，而非按单一文件数考核：** tracked files 目标 850–1050、硬上限 1200；生产源码 450–650；测试文件 250–350；默认容器 4 个。安全覆盖优先于文件数削减。

## Consequences

正面：

- 通用 Harness 能力（长流程编排、多 Agent 隔离与预算治理、sandbox、checkpoint/receipts）直接复用，工程投入集中在业务价值最高的 SQL 安全链与证据链上。
- 依赖倒置使业务域可独立测试，`domain` 层不依赖 FastAPI/LangChain/SQLAlchemy，可用纯单元测试覆盖策略与口径逻辑。
- 上游 tree 可追溯，每个 Phase 一个职责明确的主提交，可按域独立 revert。
- 保留并强化可解释的工程主题：受约束的多 Agent 分工、SQL AST 与权限/成本/只读执行的审计闭环、端口/适配器设计、SSE/artifact/scheduler 故障恢复。

代价与风险：

- 需要长期维护与上游的分叉，上游后续版本无法直接 merge；这是选定 A 路线时接受的成本。
- 删除能力时必须先做 import/router/config 三层引用扫描与 startup smoke，否则会出现「目录已删、生命周期仍引用」的高危故障。
- middleware 顺序、LLM 绕过 SQL policy、MySQL/PostgreSQL 方言差异、日志与 SSE 泄露凭据或 PII 属高风险项，需要顺序快照测试与统一 redaction 等控制措施。
- 阶段顺序强约束：先建立替代主链和契约测试，再解除引用，然后删除实现与依赖，最后清理测试与文档；禁止以目录级批量删除代替依赖分析。

## 后续阶段

Phase 0 仅建立治理层，不修改运行时。后续按架构报告的分阶段迁移计划执行：1 领域骨架 → 2 安全数据链 → 3 Agent 工作流 → 4 前端工作台 → 5 能力瘦身 → 6 部署验收。

## References

- [UPSTREAM.md](../../UPSTREAM.md) — 上游来源、版本与不可变基线记录
- [架构重构报告](../architecture/architecture-refactoring-report.md) — 本决策的依据（KEEP/MODIFY/DELETE、目标架构、Text2SQL 安全设计、分阶段迁移计划）
- [docs/PROGRESS.md](../PROGRESS.md) — 当前阶段状态与规模预算
- [验收场景](../acceptance/acceptance-scenarios.md) — 发布级验收契约
- Phase 0 实施计划：[docs/superpowers/plans/2026-09-21-phase-00-governance.md](../superpowers/plans/2026-09-21-phase-00-governance.md)
