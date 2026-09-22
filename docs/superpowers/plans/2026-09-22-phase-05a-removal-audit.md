# Phase 5A Removal Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 InsightFlow 能力瘦身建立可执行、可验证、可回滚的精确删除清单，不在本切片删除代码。

**Architecture:** 以 Git tracked tree 为唯一规模基线，从 route/lifecycle/registry/config 动态入口反向构建
依赖证据，再按依赖顺序形成 3–5 个删除批次。清单同时记录 KEEP 例外、替代主链和累计门禁，下一轮可
直接执行而无需重新侦察。

**Tech Stack:** Git, ripgrep, Python AST/import inspection, TypeScript/Next.js route inventory, YAML,
Markdown.

**Spec:** `docs/architecture/phase-05-capability-contraction.md`

## Global Constraints

- 起点必须是 `65b499d76273d303e51ebb4b26b91b0e4c2e72f1`。
- 固定 tag `upstream-v2.1.0-rc0` commit/tree 不得变化。
- 只允许新增/修改 Phase 5A 文档、`docs/PROGRESS.md` 与忽略的 `.reviews/` 证据。
- 不修改或删除任何生产、测试、config、dependency、lockfile、Docker、CI、skill 或 asset。
- 不安装依赖、不启动 Docker、不跑大测试；本切片是静态审计。
- 统计只使用 `git ls-files` 的 tracked path；untracked `.reviews`、本地配置和 build output 不计入。
- 一个 docs-only commit；Phase 5B 不启动。

---

### Task 1: 固定基线与分类口径

- [ ] 记录 HEAD、tree、tag commit/tree、tracked files、生产源码、测试、迁移、lock/generated、有效文本
  LOC 的可复现命令和结果。
- [ ] 定义生产源码/测试/有效文本 LOC 的扩展名与排除规则，避免 Phase 0 与 Phase 5 统计口径漂移。
- [ ] 列出最终路由、Gateway router、tool group、skill、sandbox、model、memory、MCP、Compose 服务的
  KEEP 白名单；任何未分类项视为审计失败。
- [ ] 写入 `docs/removal/phase-05-current-inventory.md`。

### Task 2: Frontend legacy surface 审计

- [ ] 从 `frontend/src/app` filesystem routes、导航、dynamic import、i18n、static mocks、E2E 反向扫描
  docs/blog/showcase/stars、agents、projects/trash、channels、browser、voice、capabilities。
- [ ] 对每个候选列出 delete roots/files、必须修改的共享 shell/core、KEEP exceptions、依赖和测试。
- [ ] 单独证明分析/chat/artifact/auth/scheduler/settings 在删除后的路由与数据依赖仍闭合。
- [ ] 将认证页 `deer.svg` 引用移除与资产零引用删除放入第一个执行批次。

### Task 3: Backend/Harness 产品域审计

- [ ] 从 Gateway `create_app`/lifespan/router、config schema、migration metadata、tool/skill/subagent registry、
  extension loading 和字符串 import 扫描十个候选域。
- [ ] 区分普通 subagent runtime 与 managed/custom/batch/ACP，禁止误删 `task`、timeout/cancel/receipt。
- [ ] 区分 thread/artifact ownership 主链与 projects/trash/documents/browser，写出解除耦合的 exact
  modify files。
- [ ] 历史 migration 默认 KEEP；任何表/版本链删除建议必须说明空库升级和已有库升级如何仍成立。

### Task 4: Provider、sandbox、memory、skills 与依赖审计

- [ ] 列出每个 sandbox/model/search/fetch/memory provider 的实现、config、factory/registry、依赖和测试。
- [ ] 用实际默认配置与工具主链决定一个 Web Search/Fetch 保留实现；写明选择和后果，不保留多个“备用”。
- [ ] Skills 按 KEEP business/data/chart/report/minimal-runtime 与 DELETE marketplace/evolution/media 分类，记录
  skill loader 或文档对目录名的动态引用。
- [ ] 为 Python/npm 候选依赖逐项给出“最后活跃 import 所属批次”，禁止只因名字相似删除。

### Task 5: 生成可执行 manifest 与影响报告

- [ ] 创建 `docs/removal/phase-05-deletion-manifest.yaml`，严格满足 spec schema；用现有 Python 环境
  `yaml.safe_load` 或项目实际 parser 验证可解析。
- [ ] 创建 `docs/removal/phase-05-dependency-impact.md`，每个域至少给出入口、动态引用、解除方式、替代、
  风险和回滚。
- [ ] 所有 delete path 必须当前 tracked；所有 modify/keep exception 必须当前存在；同一路径不得同时
  DELETE 与 KEEP/MODIFY。
- [ ] 计算每批 before/forecast_after 和最终预测；误差来源必须显式，不能用“约”“大概”替代数值。

### Task 6: 验证矩阵与 docs-only 提交

- [ ] 创建 `docs/removal/phase-05-verification-matrix.md`：每批 focused tests + lint/type/build/reference scan，
  最后一批包含 backend/frontend 累计回归、Gateway/Frontend smoke 和 Phase 0–4 关键契约。
- [ ] 增加 manifest 自洽检查：路径存在、分类互斥、批次无循环依赖、预测可加和、KEEP 安全测试未列删除。
- [ ] 更新 `docs/PROGRESS.md`：Phase 4 Complete，Phase 5 In progress，next gate 为 Phase 5A GPT review。
- [ ] `git diff --check`、文档 placeholder scan、lock/tag/tree/status 检查。
- [ ] 提交 `docs: audit phase 5 capability removal`；确认提交只含批准文档，工作树干净。

