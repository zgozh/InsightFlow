# Phase 5B Capability Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 Phase 5A 已验证 manifest 依序完成 B1–B5 能力删除，每批保持 KEEP 主链可运行并独立形成提交。

**Architecture:** `docs/removal/phase-05-deletion-manifest.yaml` 是唯一文件范围来源，dependency impact
解释解除方式，verification matrix 定义门禁。五批形成 B1→B5 依赖链；当前批门禁不通过时立即停止，
不执行后续批次。

**Tech Stack:** Git, uv, pytest, Ruff, Next.js/TypeScript, pnpm/Rstest/Playwright, Docker Compose config.

**Spec:** `docs/architecture/phase-05-capability-contraction.md`

## Global Constraints

- 起点必须为 Phase 5A 提交 `5af2a68` 的完整 commit；先解析实际 full SHA 并记录。
- 固定 `upstream-v2.1.0-rc0` commit/tree 不得变化。
- 严格执行 manifest B1→B5；不得提前加入 Phase 5C 的第二轮候选。
- 不新增功能、框架、服务、数据库表、migration 或容器。
- 删除使用 manifest 的 repo-relative exact roots/files；不得用未校验的递归 glob 或跨 shell 拼接路径。
- 每批一个 Conventional Commit；提交后工作树干净才进入下一批。
- 任一 focused/cumulative gate 失败且无法在该批允许范围内修复时，停止并报告，不继续后批。
- 历史 migration、ORM model、Analytics 安全链、KEEP 白名单与安全测试不得删除。
- 所有 uv 命令使用 `--locked`；只有 B4 依赖收缩可更新 lock，更新时设置
  `UV_DEFAULT_INDEX=https://pypi.org/simple` 并使用项目包管理命令重新生成，禁止手改 lock。

---

### Task 0: 执行前校验与 rollback 语义修正

- [ ] 验证 HEAD、工作树、tag/tree、manifest 可解析、自洽脚本和 last-importer 脚本 exit 0。
- [ ] 对照当前 tree 验证 manifest 所有 delete/modify path 未漂移；有漂移则停止。
- [ ] 修正文档中“任意批次可带着后续批次单独 revert”的表述：B1→B5 是依赖链，安全整链回滚必须
  B5→B1；单批 revert 只在没有后续依赖批次时成立。
- [ ] 把该文档修正随 B1 提交，不创建独立空提交。

### Task 1: B1 前端遗留面与品牌资产

- [ ] 先运行 verification matrix §2 B1 的基线门禁并记录。
- [ ] 严格应用 manifest B1 delete roots/files/modify files/keep exceptions；先移除认证页 deer mask，再在
  零活跃引用证明后删除 `deer.svg`。
- [ ] 删除 docs/blog/showcase/stars、legacy workspace routes、孤儿营销面；修剪共享 navigation、i18n、
  mock/static/performance 配置，KEEP 分析/chat/auth/artifact/scheduler 路由。
- [ ] 删除模块对应测试；混合测试只删相关用例，不删除 KEEP 断言。
- [ ] 运行 B1 focused gates、`pnpm check`、format、相关 Rstest/Playwright/build 与 reference scan。
- [ ] 记录实际计数并提交 `refactor: remove legacy frontend surfaces`。

### Task 2: B2 后端旧产品面

- [ ] 验证 B1 commit/clean tree，运行 B2 基线 focused gates。
- [ ] 删除 Channels/IM、Custom/Managed Agents、Projects/Documents/Trash/Browser/Console 的入口与实现；
  精确裁剪共享 lead/config/persistence exports，不删除普通 task/subagent、thread ownership 或 artifact。
- [ ] 从 AIO sandbox 与 sandbox tools 移除 Lark 装配，保留其余 AIO/command 主链。
- [ ] 保留历史 ORM models/migrations，只删除 store/写入/API/UI 主链；更新权限清单与 OpenAPI 契约。
- [ ] 运行 B2 focused + B1 cumulative gates、Gateway import/smoke、reference/last-importer。
- [ ] 记录实际计数并提交 `refactor: remove legacy product platforms`。

### Task 3: B3 运行期 provider 收缩

- [ ] 验证 B2 commit/clean tree，运行 B3 基线 focused gates。
- [ ] 删除 ACP/durable batch、远程 sandbox/provisioner/Helm、备用 model/search/memory providers；保留普通
  task、Local+AIO sandbox、OpenAI-compatible+DeepSeek、DDG+Jina、DeerMem+Noop、MCP tasks。
- [ ] 修改 factory/prompt/tool registry/config/wizard/doctor/frontend tool names；删除 image/knowledge search
  产品入口并记录能力损失。
- [ ] Helm 删除后把版本契约从三源改为 backend/frontend 两源并同步 release/CI 文档与脚本。
- [ ] 对 Jina fetch 明确安全事实：若剩余实现不在本机发起目标 URL 请求，则说明 SSRF 面已移除而非
  “取消防护”；若仍有本机 URL 请求，则必须保留或迁移现有 URL safety，不能以删 provider 为由降级。
- [ ] 运行 B3 focused + B1/B2 cumulative、migration bootstrap、web/tool/model/memory/sandbox gates。
- [ ] 记录实际计数并提交 `refactor: narrow runtime providers`。

### Task 4: B4 Skills、依赖、配置与 CI

- [ ] 验证 B3 commit/clean tree，运行 B4 基线 focused gates。
- [ ] 删除 manifest 指定的 skill marketplace/reviewer/creator/find 与媒体技能，并删除 Agent 运行期
  `skill_manage`/Self-Evolution；保留五个业务/基础技能、`/api/skills` 管理契约和
  loader/parser/permissions/projection/SkillScan/LLM moderation 安全门禁。
- [ ] 先扩充 B4 manifest，精确登记 self-evolution 的删除路径、配置迁移和测试范围；将旧安全扫描字段
  逐字段迁入 `skill_security`，丢弃旧 `enabled`，升级脚本保留备份并使用 `uv run --locked`。
- [ ] 仅在最后 importer 已删除后移除 Python/npm dependencies，使用 uv/pnpm 正常更新 lock；记录 added/
  removed/changed 坐标，依赖只允许减少或因解析产生不可避免的同包版本收敛，禁止新增产品依赖。
- [ ] 同步 config_version、example config、CI、README/AGENTS/backend docs；移除失效 skill review waiver/job。
- [ ] 运行 B4 focused + cumulative、`uv lock --check`、`pnpm install --frozen-lockfile`、SkillScan、
  config/version、安全扫描器、技能路由授权与 `/api/skills` 管理门禁。
- [ ] 记录实际计数并提交 `refactor: remove unused skills and dependencies`。

### Task 5: B5 孤儿清理与累计收敛

- [ ] 验证 B4 commit/clean tree。
- [ ] 严格应用 manifest B5；处理构建后已证明可删的 Nextra/MDX wrapper、mock dead branches 等 BLOCKED
  项时，只能在 verification matrix 指定的真实 build/Playwright 证据成立后删除，否则继续 KEEP 并报告。
- [ ] 清除 orphan import/string config/registry/i18n/docs/fixtures，但保留 upstream attribution、阶段决策、
  acceptance、Analytics/Harness guides。
- [ ] 跑 manifest 自洽与 last-importer；重算 tracked/source/tests/migration/text LOC，分别给出预测与实际。
- [ ] 执行 verification matrix §5 累计门禁：backend tests/lint、frontend tests/check/format/build、Gateway
  与 Frontend smoke、Compose config、Phase 0–4 核心契约。真实数据库/Docker 集成按矩阵要求；若环境
  不可用必须停止，不能把未运行写成 PASS。
- [ ] 更新文档、PROGRESS：Phase 5 仍 In progress，next gate 为 Phase 5B GPT review，Phase 5C/6 未启动。
- [ ] 提交 `refactor: converge insightflow capability surface`，工作树干净。

### Task 6: 最终执行报告

- [ ] 一次性汇报五个 commit、每批 exact delete/modify/dependency/lock/size、门禁命令与退出码。
- [ ] 列出预测偏差、保留的 BLOCKED 项、能力损失、安全边界和反向归属扫描。
- [ ] 明确 2290 不是自动接受的最终预算；等待 Phase 5C 对真实剩余 tree 做第二轮复核。
