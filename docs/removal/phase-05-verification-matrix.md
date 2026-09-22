# Phase 5 删除批次验证矩阵（Phase 5A 交付）

本文件是 Phase 5B 的执行脚本：每批删什么、跑什么、看什么。**门禁只按模块归属裁剪，
不按文件数比例裁剪。**

## 1. 批次与依赖

| 批次 | 目标 | 依赖 | 回滚 |
| --- | --- | --- | --- |
| B1 `frontend-legacy-and-brand` | 前端遗留面与品牌资产 | 无 | `git revert <B1>` |
| B2 `backend-product-faces` | IM/Custom Agent/Projects/Browser/Console 后端入口 | B1（前端调用方已消失） | `git revert <B2>` |
| B3 `runtime-surplus` | ACP/durable batch、远程 sandbox/provisioner/Helm、provider zoo、memory zoo | B2（共享 config/registry 已收敛） | `git revert <B3>` |
| B4 `skills-deps-config` | Skills/media、依赖、config 键、CI job、文档 | B3（最后一个 importer 已消失） | `git revert <B4>` |
| B5 `convergence` | 孤儿引用、i18n、README/AGENTS、规模收敛 | B4 | `git revert <B5>` |

依赖方向是**有向无环的**：只允许 B1→B2→B3→B4→B5。回滚任意一批都不得要求回滚其后批次——
每批结束时 KEEP 主链必须自洽可运行（见 §3 的逐批最小门禁）。

## 2. 每批最小门禁（focused，不通跑全量）

### B1 前端遗留面与品牌

```powershell
# 1) 品牌资产：先删除两个认证页的 mask 引用，再证明零引用
rg -n "deer\.svg" frontend/src frontend/public docker deploy
#    期望：只剩 frontend/public/images/deer.svg 自身；deploy/helm 随 B3 删除
# 2) KEEP 路由仍可达
cd frontend
pnpm exec rstest run tests/unit/core/i18n tests/unit/components/auth tests/unit/core/analytics tests/unit/components/analytics
pnpm exec playwright test tests/e2e/landing.spec.ts tests/e2e/sidebar.spec.ts tests/e2e/chat.spec.ts
pnpm exec playwright test -c playwright.auth.config.ts tests/e2e-auth
# 3) 删除的路由不再被引用
rg -n "/workspace/agents|/workspace/projects|/workspace/trash|/workspace/capabilities|/blog|/showcase|github-stars" frontend/src
#    期望：仅剩被删除文件自身（删除后为 0）
```

### B2 后端产品面

```powershell
cd backend
PYTHONPATH=. uv run --locked pytest tests/test_analytics_api.py tests/test_analytics_delivery.py `
  tests/test_analytics_composition.py tests/test_harness_boundary.py tests/test_analytics_boundaries.py `
  tests/test_threads_router.py tests/test_artifacts_router.py tests/test_uploads_router.py `
  tests/test_scheduled_tasks.py -q
# 路由权限清单必须同步更新，否则这两条会红：
uv run --locked pytest tests/test_auth_me_permissions.py -q
cd ..\frontend && pnpm exec playwright test tests/e2e-real-backend/auth-disabled-contract.spec.ts
# 被删路由必须 404 且不再出现在 OpenAPI
cd ..\backend && PYTHONPATH=. uv run --locked python -c "from app.gateway.app import create_app; app=create_app(); print(sorted({r.path for r in app.routes if getattr(r,'path','').startswith('/api/')}))"
```

### B3 运行期盈余

```powershell
cd backend
PYTHONPATH=. uv run --locked pytest tests/test_subagent_executor.py tests/test_delegation_ledger.py `
  tests/test_mcp_tools.py tests/test_memory_manager.py tests/test_deermem_fact_selection.py `
  tests/test_sandbox_leases.py tests/test_aio_sandbox_get.py -q
# provider 选择面：默认配置仍能装配出 web_search/web_fetch
PYTHONPATH=. uv run --locked pytest tests/test_config_loader.py tests/test_tool_loader.py -q
# 迁移链完整（历史 migration 一律 KEEP）
PYTHONPATH=. uv run --locked pytest tests/test_persistence_scaffold.py tests/test_persistence_forward_revision_compat.py -q
```

### B4 Skills / 依赖 / 配置 / CI

```powershell
cd backend && uv lock --check && PYTHONPATH=. uv run --locked pytest tests/test_business_analysis_skill.py -q
# Skill 安装期安全门禁（SkillScan/security scanner）必须仍然绿——它不随 review 平台删除：
PYTHONPATH=. uv run --locked pytest tests/test_skillscan_native.py tests/test_security_scanner.py tests/test_skills_installer.py tests/test_skill_manage_tool.py -q
cd ..\frontend && pnpm exec rstest run tests/unit/core/i18n tests/unit/components/analytics
# 依赖不得残留孤儿 import
rg -n "import (slack|telegram|discord|dingtalk)|from deerflow\.community\.(tavily|brave|exa|firecrawl)" backend
# 被删模块的 importer 必须全部落位（0 处遗留）：
cd .. && uv run --locked --project backend python .reviews/phase-05-last-importer.py docs/removal/phase-05-deletion-manifest.yaml
```

### B5 收敛

```powershell
# 孤儿引用扫描：被删模块的字符串路径、config `use:`、registry 名、i18n 命名空间
rg -n "deerflow\.community\.(e2b_sandbox|boxlite|opensandbox|tenki|tavily|brave|exa|firecrawl|fastcrw|groundroute|serply|sofya|serper|searxng|infoquest|crawl4ai|ragflow|lightrag|tencent_wsa|image_search)" .
rg -n "deerflow\.models\.(claude_provider|mindie_provider|openai_codex_provider|patched_mimo|patched_minimax|patched_stepfun|vllm_provider)" .
rg -n "app\.channels|routers\.(agents|projects|trash|browser|console|subagents|subagent_batches|channels|channel_connections|integrations|github_webhooks|assistants_compat)" .
python .reviews/phase-05-count.py   # 规模收敛证据（Phase 5B 复跑同一脚本）
```

## 3. 每批之后必须仍然成立的不变量

无论哪一批，以下断言都必须为真；任何一条变红即该批不可提交：

1. `backend/tests/test_harness_boundary.py` 绿（Harness 不 import `app.*`）。
2. `backend/tests/test_analytics_boundaries.py` 绿（Analytics 分层与依赖方向不变）。
3. Analytics 安全闭环全绿：`test_analytics_domain`、`test_sql_policy`、`test_semantic_authorizer`、
   `test_authorize_prepared_query`、`test_query_policy_domain`、`test_analytics_delivery`、
   `test_analytics_api`、`test_analytics_report_domain`、`test_analytics_reports_persistence`、
   `test_analytics_agent_reports`、`test_analytics_agent_tools`、`test_analytics_agent_evidence`、
   `test_analytics_persistence_migrations`、`test_analytics_composition`。
4. Thread ownership / artifact 下载 / 上传 仍受 `require_permission(..., owner_check=True)` 保护：
   `test_owner_isolation.py`、`test_artifacts_router.py`、`test_uploads_router.py` 绿。
5. Scheduler 主链绿：`test_scheduled_tasks.py`、`test_scheduled_run_history.py`（前端）。
6. Run/SSE/checkpoint/receipt 主链绿：`test_runtime_lifecycle_e2e.py`、`test_run_worker_delivery.py`、
   `test_run_worker_rollback.py`、`test_checkpoint_state.py`、`test_run_event_stream_contract.py`。
7. 普通 `task` 委派与超时/取消/令牌/回执/循环护栏不变：`test_subagent_executor.py`、
   `test_turn_budget.py`、`test_token_collector.py`、`test_loop_detection_middleware.py` 绿。
8. 前端 KEEP 路由可渲染：Playwright `landing/sidebar/chat/insightflow-workspace` +
   `e2e-auth`（`auth-setup-recovery`、`visible-brand`）全绿。
9. `git diff --check` exit 0（默认，不加 `core.whitespace` 覆盖）。
10. 固定 tag `upstream-v2.1.0-rc0` 的 commit/tree 未变；`backend/uv.lock`、`frontend/pnpm-lock.yaml`
    只在 B4 因移除依赖而变更，且必须 `uv lock --check` 与 `pnpm install --frozen-lockfile` 通过。
11. **引用证明不退化**：`.reviews/phase-05-last-importer.py` 在本批结束时仍报 `survivors: {}`
    （被删模块的每个 importer 要么自身已删，要么已在本批或前批登记的 `modify_files` 内）。

## 4. 测试清理规则

删除测试的唯一依据是**它测的模块被删了**，而不是"文件数超标"：

- 被删模块的专属测试随模块删除；跨模块的共享 fixture/helper（如 `backend/tests/conftest.py`、
  `tests/support/**`）只在最后一个使用者消失后删除，且必须同时更新 `conftest.py` 的
  `sys.modules` mock（`deerflow.subagents.executor` 那一条必须保留）。
- `backend/tests/blocking_io/**` 是 CI 硬门禁（`backend-blocking-io-tests.yml`）。它里面针对被删模块的
  条目可以删，但 `conftest.py`、`test_gate_smoke.py` 与覆盖 KEEP 模块的条目必须保留。
- Phase 0–4 建立的安全测试（§3.1–§3.3、§3.6）**任何批次都不得删除**；manifest 自洽脚本会对此报错。
- 前端 `tests/e2e/**` 中 KEEP 路由的 spec 必须保留；被删路由的 spec 随路由删除。
- 不允许用 `--update-snapshots` 或放宽断言来让门禁变绿。

## 5. 累计门禁（B5 结束时）

```powershell
cd backend && uv lock --check && uv run --locked ruff check app packages && uv run --locked ruff format --check app packages
PYTHONPATH=. uv run --locked pytest tests -q          # 全量后端（已删除的模块不再有测试）
cd ..\frontend && pnpm check && pnpm format && pnpm exec rstest run && pnpm build
pnpm exec playwright test tests/e2e tests/e2e-auth
```

外加：

- 清单自洽与引用证明复跑：`uv run --locked --project backend python .reviews/phase-05-manifest-check.py docs/removal/phase-05-deletion-manifest.yaml`
  与 `.reviews/phase-05-last-importer.py` 都必须 exit 0；
- `scripts/verify_versions.sh`（配置版本号若因删除键而改变，必须同步 `config_version`）；
- `make check` 与 `make dev` 的 Gateway `/health`、`/health/ready` 冒烟；
- `python scripts/test_analytics_databases.py --engine all`（Phase 2B2 真实数据库门禁，
  只有 Docker 可用时才跑；不可用时必须在报告里写"未跑"而不是"通过"）；
- `docs/acceptance/acceptance-scenarios.md` 的发布级验收场景逐条复核。

## 6. 规模收敛判定

`python .reviews/phase-05-count.py` 在 B5 结束时复跑一次，与 `phase-05-deletion-manifest.yaml`
的 `forecast_after` 逐项对账。口径必须与 `phase-05-current-inventory.md` §2 完全一致。

对账结果只有两种合法结论：

1. **达到 850–1050**：manifest 的预测与实际差值在 ±3% 内，逐项列出误差来源；
2. **达不到**：给出按域计算的保守最小值，并逐条列出"不可删 KEEP 成本"（该域为什么不能再删）。

不允许写"约"、"大概"或跳过对账。安全测试不参与规模收敛。

### 6.1 Phase 5A 已给出的判定：结论 2（达不到）

按域审计后的最大可删集合为 783 tracked 文件，删除后仍有 2290 tracked / 1060 source / 894 tests /
547896 text-LOC，均高于目标区间与硬上限（详见 `phase-05-deletion-manifest.yaml` 的
`target_verdict` 与 `keep_cost_breakdown`、以及 `phase-05-dependency-impact.md` §4）。
因此 Phase 5B 的验收口径是：

- **规模项按保守最小值验收**：B5 结束时 `phase-05-count.py` 的实测值必须落在
  `forecast_after` 的 ±3% 以内，且逐项给出误差来源；
- **不允许为了逼近 850–1050 而删除 KEEP 契约内的东西**：安全测试、Analytics 分层、
  Harness 边界、前端 KEEP 路由与其测试、Alembic 链、ORM model 一律不参与规模收敛；
- 若要对齐 Phase 0 的数字目标，必须先修改 KEEP 契约（产品决策），本阶段无权执行。
