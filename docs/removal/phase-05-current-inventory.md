# Phase 5 当前规模与最终 KEEP 表面（Phase 5A 审计）

本文件是 Phase 5A 的基线快照：**只统计、不修改**。所有数字都可用文中的命令复现。

## 1. 基线坐标

```powershell
git rev-parse HEAD                 # 65b499d76273d303e51ebb4b26b91b0e4c2e72f1
git show -s --format=%T HEAD       # 5fe3349238e216091f5aa385136ad2cb4284e628
git show -s --format=%H upstream-v2.1.0-rc0   # 609bfde0ced76ff0a58c02ff5c741df768f44502
git show -s --format=%T upstream-v2.1.0-rc0   # 2473c22e163a3879490848a7995eb2b7be7f6f50
```

| 项 | 值 |
| --- | --- |
| 基线提交 | `65b499d76273d303e51ebb4b26b91b0e4c2e72f1` |
| 基线 tree | `5fe3349238e216091f5aa385136ad2cb4284e628` |
| 固定 tag `upstream-v2.1.0-rc0` | `609bfde0ced76ff0a58c02ff5c741df768f44502` / tree `2473c22e163a3879490848a7995eb2b7be7f6f50`（不得移动） |
| Phase 5A 交付 | 仅四份 `docs/removal/phase-05-*.md|yaml` + `docs/PROGRESS.md` + 本阶段提示词 |

## 2. 统计口径（唯一口径，禁止各批自定义）

统计脚本：`.reviews/phase-05-count.py`（本地、忽略、不提交）。数据源只有一个：
`git ls-files`（tracked-only）。untracked 的 `.reviews/`、本地 `config.yaml`、
`extensions_config.json`、`.next/`、`node_modules/` 一律不计入。

| 类别 | 规则 |
| --- | --- |
| TEST | 路径以 `tests/` 开头或含 `/tests/`；或文件名匹配 `test_*.py`、`*_test.py`、`conftest.py`、`*.test.ts(x)`、`*.spec.ts(x)`、`*.dom.test.ts(x)` |
| MIGRATION | 路径含 `/migrations/versions/` 或 `/alembic/versions/` |
| GENERATED | `uv.lock`、`pnpm-lock.yaml`、`package-lock.json`、`*.min.js`、`*.min.css`、`*.d.ts`、图片/字体等二进制资产 |
| SOURCE | 扩展名 ∈ {`.py`,`.ts`,`.tsx`,`.js`,`.jsx`,`.mjs`,`.cjs`,`.sh`,`.ps1`,`.sql`,`.css`,`.scss`,`.html`,`.vue`} 且不属于 TEST/MIGRATION/GENERATED |
| TEXT_LOC | SOURCE+TEST 中扩展名 ∈ TEXT 集的文件行数（按 LF 计数）之和 |

## 3. 当前规模

```powershell
python .reviews/phase-05-count.py
```

| 指标 | 当前 | 目标区间 | 硬上限 |
| --- | ---: | ---: | ---: |
| tracked files | **3073** | 850–1050 | 1200 |
| 生产源码 SOURCE | **1399** | 450–650 | — |
| 测试 TEST | **1078** | 250–350 | — |
| migration | **29** | — | 历史 migration 默认 KEEP |
| 生成/二进制 | 37 | — | — |
| 有效文本 LOC | **717429** | 140k–220k | — |

按子树拆分（同上口径）：

| 子树 | tracked | source | tests | migrations | text LOC |
| --- | ---: | ---: | ---: | ---: | ---: |
| `backend/` | 1718 | 766 | 803 | 29 | 546248 |
| `frontend/` | 940 | 536 | 266 | 0 | 149146 |
| `docs/` | 129 | 14 | 1 | 0 | 1771 |
| `skills/` | 105 | 25 | 0 | 0 | 7396 |
| `scripts/` | 46 | 43 | 1 | 0 | 8961 |
| `deploy/` | 27 | 0 | 0 | 0 | 0 |
| `docker/` | 21 | 5 | 0 | 0 | 1698 |
| `.github/` | 23 | 0 | 0 | 0 | 0 |
| `contracts/` | 7 | 0 | 0 | 0 | 0 |
| `examples/` | 6 | 2 | 2 | 0 | 395 |

**规模结论（提前给出，供第 5–7 节引用）**：当前 3073 tracked 相对目标上限 1050 需要减少
**≥2023** 个文件；相对硬上限 1200 需要减少 **≥1873**。删减量必须由第 4 节的 KEEP 白名单
与第 5 节的批次预测共同证明，不允许靠"按比例删测试"达成。

## 4. 最终 KEEP 白名单

KEEP 以**能力**为单位，不以目录为单位；下面的每一条都能在 Phase 5B 的引用扫描中被逐条复核。

### 4.1 Gateway 路由（`backend/app/gateway/app.py` 的 `include_router` 全集）

`app.py` 共注册 33 个 router。每一个都必须落进 KEEP 或某个 DELETE 域，不允许"未分类"：

| Router | 决定 | 依据 |
| --- | --- | --- |
| `auth` | KEEP | 认证主链 |
| `user_preferences` | KEEP | 账号偏好（设置页数据源） |
| `models` | KEEP | 模型目录（工作台模型选择） |
| `features` | KEEP | 能力开关（前端按它决定可选面板） |
| `threads` | KEEP | Thread/Artifact/Upload 主链 |
| `thread_runs` | KEEP | Run + SSE 主链 |
| `runs` | KEEP | 无状态 run |
| `artifacts` | KEEP | Artifact 下载/编辑（thread ownership） |
| `uploads` | KEEP | Upload 主链 |
| `scheduled_tasks` | KEEP | Scheduler |
| `analytics` | KEEP | Analytics 安全主链 |
| `mcp` | KEEP | MCP discovery/session/invocation |
| `mcp_tasks` | KEEP | MCP 长程任务的持久化投影 |
| `memory` | KEEP | DeerMem/Noop + 偏好主链 |
| `skills` | KEEP | Skill loader/policy/activation（含 install/reload） |
| `suggestions` | KEEP | 会话跟进问题（十域之外，保守保留） |
| `input_polish` | KEEP | 发送前草稿改写（十域之外，保守保留） |
| `feedback` | KEEP | 运行反馈（十域之外，保守保留） |
| `console` | DELETE（域 1 观测面） | 跨线程观测台：全仓唯一调用方是它自己的 router 与 `backend/tests/test_console_router.py`，前端无任何 `/api/console` 调用（见 `phase-05-dependency-impact.md`） |
| `agents` | DELETE（域 3） | Custom/Managed Agent；前端 `core/agents/api.ts` 调用 `/api/agents/**`，随 UI 一起删 |
| `subagents` | DELETE（域 3） | managed subagent CRUD |
| `subagent_batches` | DELETE（域 4） | durable batch |
| `assistants_compat` | DELETE（域 3） | LangGraph assistants 兼容桩。**证据**：`@langchain/langgraph-sdk` 1.5.3 的 `dist/**` 里 `assistants.get/search/count/create` 被调用次数为 **0**（只有 `AssistantsClient` 的方法定义）；`frontend/src/**` 里 `/assistants` 出现次数为 **0**；`useStream({assistantId:"lead_agent"})`（`core/threads/hooks.ts:1852`）只把 `assistantId` 转交给被覆写的 `client.runs.stream`（`core/api/api-client.ts:459`）；`tests/e2e/utils/mock-api.ts` 未 mock `/assistants`，而 chat/sidecar/thread 三套 E2E 在 `next start` 下全绿 —— 说明 KEEP 主链不会发这个请求 |
| `projects` | DELETE（域 5） | Projects |
| `project_documents` | DELETE（域 5） | Documents |
| `project_thread_files` | DELETE（域 5） | 项目文件 |
| `trash` | DELETE（域 5） | Trash |
| `browser` | DELETE（域 5） | Browser 控制 |
| `channels` | DELETE（域 2） | IM 渠道 |
| `channel_connections` | DELETE（域 2） | IM 连接管理 |
| `integrations` | DELETE（域 2） | Lark/Feishu 托管集成 |
| `github_webhooks` | DELETE（域 2） | GitHub channel |

### 4.2 Harness 主链（KEEP）

- Lead agent：`backend/packages/harness/deerflow/agents/lead_agent/**`、`factory.py`、`goal_state.py`、`human_input.py`。
- Middleware 主链：`agents/middlewares/**`（timeout/cancel/token/receipt/loop guard、
  clarification、summarization、title、todo、skill activation/policy、MCP routing、read-before-write）。
- 普通 subagent runtime：`subagents/{executor,registry,runtime,config,capacity,turn_budget,token_collector,step_events,status_contract,report_contract,context_snapshot,acceptance_checks}.py`
  与 `subagents/builtins/{general_purpose,bash_agent}.py`；`task` 工具语义不变。
- Runtime：`packages/harness/deerflow/runtime/**`（RunManager/RunStore/worker/journal/events/checkpoint）。
- Persistence：`packages/harness/deerflow/persistence/**` 与其 Alembic 链（**历史 migration 全部 KEEP**）。
- Sandbox：`sandbox/**` 的抽象层 + `sandbox/local/**` + `community/aio_sandbox/**`。
- Models：`models/factory.py`、`patched_openai.py`、`patched_deepseek.py`、`credential_loader.py`、
  `request_admission.py`、`assistant_payload_replay.py`。
- Search/fetch：`community/ddg_search/**`（web_search，默认无 key）+ `community/jina_ai/**`（web_fetch，默认无 key）；
  裁决证据见 `phase-05-dependency-impact.md` 第 2 节。
- Memory：`agents/memory/backends/deermem/**` + `noop/**` + `manager.py`、`tools.py`、`summarization_hook.py`。
- Skills runtime：`skills/**` 的 loader/discovery/policy/activation + `background-tasks` 无关；
  技能目录白名单见 4.4。
- MCP：`packages/harness/deerflow/mcp/**` + `app/mcp_tasks/**`。
- Analytics：`backend/app/analytics/**` 全层 + `backend/app/gateway/routers/analytics` 相关装配。

### 4.3 工具组白名单（`config.example.yaml`）

KEEP：`web`（去掉 image_search 后）、`file:read`、`file:write`、`bash`、`analytics`。
DELETE：`browser`、`knowledge`（仅为 RAGFlow/LightRAG `knowledge_search` 服务，属域 7）。

### 4.4 Skills 白名单

KEEP：`skills/public/business-analysis`、`data-analysis`、`chart-visualization`、`consulting-analysis`、`bootstrap`。
DELETE：其余 19 个目录（媒体生成、marketplace/creator/reviewer/find、research/writing、deploy 等），
逐个归类见 manifest 的 `skill_platform_media` 域。

### 4.5 部署面白名单

KEEP：`docker/{docker-compose.yaml,docker-compose-dev.yaml,docker-compose.analytics-test.yml,docker-compose.dood.yaml,nginx/**,dev-entrypoint.sh,sandbox-network-proxy/**}`。
`docker-compose.dood.yaml` 是 **KEEP**：它把宿主 Docker socket 挂进 gateway，让 `AioSandboxProvider` 的纯
Docker 模式能起每线程 sandbox 容器（`config.yaml: sandbox.use: deerflow.community.aio_sandbox:AioSandboxProvider`，
不带 `provisioner_url`），属于 KEEP 的 AIO sandbox 路径。

DELETE：`deploy/helm/**`（K8s provisioner 面）、`docker/provisioner/**`、
`docker/lark-cli-{broker,init}/**`（Lark 托管集成）、`docker/docker-compose.openviking.yaml`（OpenViking memory）、
`docker/docker-compose.cli-auth.yaml`（Claude Code / Codex CLI 凭证 + ACP agents）。

### 4.6 前端路由白名单

KEEP：`/`（Landing）、`(auth)/login`、`(auth)/setup`、`(auth)/auth/callback`、`/workspace`、
`/workspace/analysis/{new,[thread_id]}`、`/workspace/chats[/{thread_id}]`、`/workspace/datasources`、
`/workspace/metrics`、`/workspace/reports`、`/workspace/history`、`/workspace/scheduled-tasks`、
`/artifacts/view`、`/api/memory/*`。

DELETE：`/blog/**`、`/{lang}/docs/**`、`/showcase/**`、`/github-stars`、`/workspace/agents/**`、
`/workspace/projects/**`、`/workspace/trash`、`/workspace/capabilities`、`/mock/**`（静态演示夹具，
随被测路由一起裁决，见 manifest `frontend_legacy_surface`）。

## 5. 未分类项检查

Phase 5A 的验收要求"任何未分类项视为审计失败"。本文件把以下全集逐一分类，因此不存在未分类面：

1. `backend/app/gateway/routers/**` 的 33 个 router → §4.1；
2. `backend/app/` 的 7 个顶层包 → §4.1/§4.2；
3. `config.example.yaml` 的 7 个 tool group → §4.3；
4. `skills/**` 的 24 个技能目录 → §4.4；
5. `docker/**` 与 `deploy/**` 的部署面 → §4.5；
6. `frontend/src/app/**` 的 50 个 route 文件 → §4.6；
7. 下辖的 10 个候选 DELETE 域 + `deer.svg` → manifest `coverage`。

`docs/`、`contracts/`、`examples/`、`.github/`、`scripts/` 属于域 10（依赖/配置/测试/文档），
其删除项在对应批次里逐文件列出，不在此处按目录整体裁决。
