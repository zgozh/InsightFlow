# InsightFlow Product Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将受控 Analytics workflow 交付为中文优先、可管理、可审计并可演示的 InsightFlow 产品工作台。

**Architecture:** 复用现有 LangGraph chat/SSE/artifact 主链，在前端增加严格解析的 Analytics 数据层与
纯消息投影轨迹；在 App-owned Analytics bounded context 中补齐报告索引和 Lead-only 发布工具。旧能力
删除留给 Phase 5，避免新增产品功能与破坏性瘦身混在一个提交。

**Tech Stack:** FastAPI, SQLAlchemy Async, Alembic, LangChain tools, Next.js 16, React 19,
TypeScript 5.8, TanStack Query, Zod, Tailwind 4, Rstest, Playwright.

**Spec:** `docs/architecture/phase-04-insightflow-product-workspace.md`

## Global Constraints

- 起点必须为 Phase 3 提交 `7bd21d7721e3caf3cc7cc1b90bb9d3b51b7b2d8a`；固定
  `upstream-v2.1.0-rc0` commit/tree 不得变化。
- 不新增依赖、容器、数据库、Redis、队列或后台线程；`backend/uv.lock`、
  `frontend/pnpm-lock.yaml` 不得变化。
- Harness 不得 import `app.*`；前端不得实现 SQL policy、授权或摘要算法。
- 中文优先，新增用户文案全部进入 `zh-CN`/`en-US` i18n。
- 不删除旧模块/路由/依赖，不修改 Docker；Phase 5 才执行 capability removal。
- 一个最终实现提交；生产文件新增/修改建议不超过 34 个，硬上限 42 个。测试、文档、迁移与
  i18n locale 文件不计入生产文件预算。
- TDD 证据写入忽略的 `.reviews/phase-04-implementation-report.md`，不得提交。

---

## Planned File Structure

后端优先在下列既有模块内扩展，实际名称若有冲突必须先停并报告：

- `backend/app/analytics/domain/report.py`：报告值对象与严格不变量。
- `backend/app/analytics/application/report_ports.py`：repository 端口。
- `backend/app/analytics/application/reports.py`：publish/list 用例。
- `backend/app/analytics/infrastructure/persistence/models.py`：report model。
- `backend/app/analytics/infrastructure/persistence/reports.py`：SQL repository。
- `backend/app/analytics/infrastructure/persistence/migrations/versions/0002_analytics_reports.py`：前向迁移。
- `backend/app/analytics/agent/reports.py`：Lead-only publish tool。
- 既有 `composition.py`、Analytics API models/router、agent `__init__`、config.example、business-analysis skill。

前端新增：

- `frontend/src/core/analytics/{types,schemas,api,hooks,trace}.ts`。
- `frontend/src/components/analytics/`：catalog、admin forms、audit/report tables、evidence/trace panel。
- App routes：`workspace/analysis/{new,[thread_id]}`、`datasources`、`metrics`、`reports`、`history`。

前端修改：workspace sidebar/header/nav、Landing/root metadata/welcome、i18n locales 与 `frontend/AGENTS.md`。
测试放在对应 `backend/tests/`、`frontend/tests/unit/` 与 `frontend/tests/e2e/`。

---

### Task 1: 可行性与契约钉死

- [ ] 读取根、backend、analytics、frontend 的全部适用 `AGENTS.md`，核对 Phase 4 spec。
- [ ] 证明 runtime 可从受信 context/config 取得 `principal_id`、`thread_id`、`run_id`，且 subagent
  可以通过现有 additive denylist 排除 `publish_analysis_report`。
- [ ] 证明现有 artifact URL 最终经过 thread ownership；禁止创建公共 artifact URL。
- [ ] 盘点现有 chat route、message shape、tool result 配对和 history replay，确认 trace 是纯投影而非
  第二状态源。
- [ ] 把证据写入 report。若任一项不成立，只报告最小 seam，不写生产代码、不提交。

### Task 2: 报告领域、持久化与迁移（TDD）

- [ ] 先新增失败测试：值对象拒绝不可信 ID、坏 SHA-256、超过上限 evidence、越界 artifact path；
  repository principal 隔离、稳定 keyset、幂等唯一发布；损坏行整页失败。
- [ ] 实现 immutable `AnalysisReport`、`ReportStatus` 和稳定错误 reason，不保存敏感字段。
- [ ] 新增 `analytics_analysis_reports` 与 Analytics 自有 0002 migration；Harness metadata 与迁移链
  不得拥有该表。
- [ ] PostgreSQL/SQLite 验证 upgrade 0001→head、重复 bootstrap、并发幂等发布和 principal 隔离。
- [ ] 运行该任务 focused pytest、ruff、迁移边界测试并记录 RED/GREEN。

### Task 3: 报告应用用例、工具与 API（TDD）

- [ ] 先写失败测试：publish 只接受 `title/artifact_path/evidence_ids`，身份与 thread/run 均从 runtime；
  缺失上下文 fail closed；不读 artifact 内容；异常只回稳定 code。
- [ ] 实现 `PublishAnalysisReport`/`ListAnalysisReports`，幂等键由服务端派生。
- [ ] 实现 `publish_analysis_report` 并注册 Analytics tool group；在
  `subagents.agents.general-purpose.disallowed_tools` 与 bash 对应配置中拒绝它，端到端断言实际 subagent
  tool schema 不含该工具、Lead 含该工具。
- [ ] 更新 business-analysis skill：`present_files` 成功后再 publish；发布失败如实说明。工具参数或结果
  不含 principal/thread/run/token/credential/SQL/result rows。
- [ ] 增加 `GET /api/analytics/reports` 的 principal-scoped keyset API；如实现 admin 查询，必须使用
  `/admin/reports?principal_id=...` 且走 admin router dependency。
- [ ] API DTO `extra="forbid"`，分页游标成对出现；响应只含报告安全索引字段。
- [ ] 运行 agent、API、repository、migration、guidance focused tests 与 ruff。

### Task 4: 前端 Analytics 数据层（TDD）

- [ ] 为 schemas 写失败测试，逐字钉住 API 字段白名单，并覆盖 unknown/missing/wrong type、Decimal
  字符串、datetime、cursor 成对语义和敏感字段注入。
- [ ] 实现 types + Zod schemas；禁止 `z.passthrough()`。
- [ ] 为 api 写失败测试，断言路径、method、JSON body、认证 fetcher、CSRF 继承和脱敏错误。
- [ ] 实现 datasource/schema/policy/metric/audit/report API client；不得把 SQL/token/secret 放入 query key
  或 error message。管理员的 opaque `secret_ref` 仅在必要表单中出现。
- [ ] 实现 Query hooks 和精确 invalidation；分页遵循后端 keyset，不无限缓存敏感历史。
- [ ] 运行该目录 node unit tests、lint/typecheck focused 检查。

### Task 5: 数据源、指标、历史与报告页面（TDD）

- [ ] 先写 DOM 测试覆盖 loading/empty/error/403、普通用户只读、管理员表单、重复提交禁用、
  stale/version drift 刷新提示、危险操作确认和键盘焦点。
- [ ] 实现 `/workspace/datasources`：普通目录 + 管理员 datasource/schema/policy 管理。禁止原始 JSON
  未校验直传，engine 更新不可变。
- [ ] 实现 `/workspace/metrics`：只读目录 + 管理员版本化管理/退役；前端不求值 expression。
- [ ] 实现 `/workspace/history`：安全字段、keyset 下一页、hash/digest 缩略与复制，不显示 SQL/rows。
- [ ] 实现 `/workspace/reports`：报告索引、evidence IDs、打开所属分析、经现有 ownership API 打开 artifact。
- [ ] 四页在 375/768/1024/1440 无水平滚动；table 在窄屏转为 card 或有明确的内部滚动容器。

### Task 6: 分析路由与结构化轨迹（TDD）

- [ ] 新增纯函数 trace parser 的失败测试：乱序、重复、stream replay、未知工具、畸形 JSON、拒绝 code、
  成功 evidence、task/present/publish；输出不得含 SQL、rows、token、DSN、异常文本。
- [ ] 实现 trace model/parser，使用 tool call ID 配对；稳定排序并去重，不读取 chain-of-thought。
- [ ] 新增 DOM 测试：状态文本+图标、evidence copy、折叠/展开、移动端 drawer、键盘操作、未知事件。
- [ ] 实现 `AnalyticsTracePanel` 并接入既有 chat layout；只在 Analytics 分析路由显示。
- [ ] `/workspace/analysis/new` 与 `/workspace/analysis/[thread_id]` 复用现有创建/stream/history/artifact
  主链，不复制 hooks，不改变 `/workspace/chats/**` 兼容性。
- [ ] 轨迹不得渲染 `query_business_data.args.sql` 或 result rows；结果表仍由既有消息/artifact UI 承担。

### Task 7: InsightFlow 品牌、导航与 i18n（TDD）

- [ ] 先写 branding/i18n/nav 测试：默认 title、workspace header、welcome/Landing、导航目标、About 上游归属；
  用户 UI 不含 deerflow.tech、ByteDance GitHub、support 邮件或 stars CTA。
- [ ] root metadata、Landing、workspace header/welcome/nav 改为 InsightFlow；Landing 只保留产品价值、
  安全能力、工作流和进入工作台 CTA，不引入图片生成资产或新网络字体。
- [ ] Sidebar 一级项固定为：新建分析、经营分析、数据源、指标中心、分析报告、定时任务、历史分析、
  系统设置。旧能力入口本阶段可留在“更多/兼容”但不得作为默认主导航。
- [ ] 所有新文案提供中文/英文；About 保留 DeerFlow v2.1.0-rc0 派生说明和 MIT attribution。
- [ ] 更新 `frontend/AGENTS.md` 记录 Analytics 数据层、trace 安全投影与报告路由约束。

### Task 8: 门禁、报告与单提交

- [ ] 后端：`uv lock --check`；报告/agent/API/migration/Phase 3 focused pytest；Analytics + 改动 Harness
  ruff check/format check；必要的 PostgreSQL 持久化测试。所有 uv 命令使用 `--locked`。
- [ ] 前端：Analytics focused unit tests、相关现有 chat/artifact/i18n tests、focused Playwright、
  `pnpm check`、`pnpm format`、`pnpm build`。不得用更新 snapshot 掩盖敏感字段或可访问性失败。
- [ ] 运行品牌扫描并分类：MIT/README/上游归属允许保留；用户可见 DeerFlow 官方 CTA 为失败；Phase 5
  待删除源码残留写入报告但本阶段不擅自删除。
- [ ] `git diff --check`；确认两份 lock、Docker、固定 tag/tree 未变，`.reviews/` 未提交。
- [ ] 更新 `docs/PROGRESS.md`：Phase 3 Complete，Phase 4 保持 In progress、next gate 为 GPT 复验；
  Phase 5 不启动。
- [ ] 仅创建提交 `feat: deliver insightflow product workspace`，工作树保持干净。
