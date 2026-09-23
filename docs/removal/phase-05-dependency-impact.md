# Phase 5 依赖影响与解除方案（Phase 5A 交付）

本文件回答一个问题：**删掉每个候选域时，究竟要从哪些入口上把它摘下来，摘不干净会断在哪里。**
它是 `docs/removal/phase-05-deletion-manifest.yaml` 的自然语言解释，两者必须逐条对得上。

Phase 5A 不修改任何生产代码、测试、依赖、配置或资产；本文件里的"删除/修改"全部是 Phase 5B 的执行指令。

## 0. 证据与可复现命令

所有结论都由三个本地脚本产出，脚本位于 gitignored 的 `.reviews/`，只在 Phase 5B 复跑，不提交：

| 脚本 | 作用 | 复现命令（仓库根目录） |
| --- | --- | --- |
| `.reviews/phase-05-count.py` | 规模与口径（`git ls-files` tracked-only） | `uv run --locked --project backend python .reviews/phase-05-count.py` |
| `.reviews/phase-05-manifest-check.py` | 清单自洽：路径存在、分类互斥、预测可加和、十域覆盖、安全测试未被删 | `uv run --locked --project backend python .reviews/phase-05-manifest-check.py docs/removal/phase-05-deletion-manifest.yaml` |
| `.reviews/phase-05-last-importer.py` | **最后引用者证明**：被删 Python 模块的每个 importer 必须自身被删或已被显式修改 | `uv run --locked --project backend python .reviews/phase-05-last-importer.py docs/removal/phase-05-deletion-manifest.yaml` |

Phase 5A 结束时的实测结果：

- `phase-05-manifest-check.py`：`errors: []`，`OK manifest is self-consistent`。
- `phase-05-last-importer.py`：`survivors: {}`，`OK every importer of a deleted module is itself deleted or explicitly modified`。
  168 个被删 Python 模块的引用者全部落位（要么自身被删，要么登记为 modify，0 处遗留），这是架构文档 §6 要求的引用证明的机器可验证形式。
  对账前该证明曾报出 87 处遗留（45 个模块分组），全部已在清单里补齐——这 87 处正是"只跑 `rg` 看不出引用"的那一类。
- 删除集合共 783 tracked 文件，修改集合 120 个文件，目录级 `keep_exceptions` 13 个。

## 1. 批次序与依赖方向

删除顺序不可交换，理由是**共享入口必须先收敛再删实现**：

| 批次 | 域 | 为什么必须在这个位置 |
| --- | --- | --- |
| B1 | 前端遗留面 + `deer.svg` | 先让后端删除域的**前端调用方**消失，B2 才有"零前端引用"的前提 |
| B2 | IM/Channels、Custom/Managed Agent、Projects/Documents/Trash、Browser、Console | 删掉 `app.gateway` 的 12 个 router 与 `app.channels` 全树；`deerflow.integrations` 是 B2 与 B3 共享的依赖，必须先删 |
| B3 | ACP/durable batch、远程 sandbox/provisioner/Helm、provider zoo、memory zoo | 依赖 B2 已收敛的 config/registry；`models/factory.py` 等共享装配文件必须与本批同时改 |
| B4 | Skill 平台/媒体技能、依赖、配置键、CI job、文档 | 只有 B3 删掉最后一个 importer 后，依赖与 extras 才能安全移除 |
| B5 | 收敛：孤儿引用、i18n、README/AGENTS、历史文档与实验资产 | 收尾批，只做"最后一公里"对齐 |

每批结束时 KEEP 主链必须自洽（门禁见 `phase-05-verification-matrix.md` §3）。
**回滚语义（Phase 5B 修正）**：B1→B5 是依赖链，整链回滚必须逆序 B5→B1；单批 `git revert <Bn>`
只在其后批次尚未应用时成立。Phase 5A 曾写成"任意批次可单独 revert"，该表述过强，已在
`phase-05-verification-matrix.md` §1.1 更正。

## 2. 逐域依赖影响

### 2.1 Frontend legacy surface（B1）

- **入口**：`frontend/src/app/blog/**`、`app/[lang]/**`、`app/showcase/**`、`app/github-stars/**`、`app/workspace/{agents,projects,trash,capabilities,channels,browser,voice}/**`、`components/landing/sections/**`（孤儿营销区块）、`content/{en,zh}/**`（88 个 MDX，nextra 文档站内容）。
- **静态引用**：`landing/header.tsx:40,46`、`landing/mobile-nav.tsx`、`landing/footer.tsx`（`/docs`、`/blog/posts` 链接）；`workspace-nav-chat-list.tsx:216`（capabilities 入口）；`workspace-container.tsx` 的 `LINKABLE_SECTIONS`。
- **动态引用**：`next/dynamic`（`command-palette.tsx` 只保留 `/workspace/chats/new`）；`core/threads/utils.ts::pathOfThread` 的 custom agent 分支；`core/threads/static-demo.ts:22`（`SHOWCASE_ROUTE_PREFIX`）；`core/api/static-response.ts:43`（`/mock/api` 兜底）；`core/i18n/locales/{zh-CN,en-US,types}.ts` 的 capabilities/agents/channels 命名空间；`frontend/tests/e2e/utils/mock-api.ts` 中只服务被删 spec 的 `page.route` 分支；`performance-budgets.json` 的 fixture 路由清单。
- **解除方式**：先按 §4.1 清 `deer.svg` 可见引用（登录/初始化页），删路由与孤儿组件，再修剪共享外壳（导航、i18n、mock、perf fixture）。`mock-api.ts` 与 `performance-budgets.json` 是**修剪不是删除**。
- **替代**：KEEP 路由为 `/`、`/login`、`/setup`、`/auth/callback`、`/workspace`、`/workspace/analysis/**`、`/workspace/chats/**`、`/workspace/{datasources,metrics,reports,history,scheduled-tasks}`、`/artifacts/view`、`/api/memory/**`。
- **风险**：`components/landing/section.tsx`（KEEP）与 `sections/**`（删）名字相近但用途不同；`thread-channel-source.tsx` 是 KEEP，因此 `components/workspace/channels` 删除时必须把 `channel-provider-icon.tsx`、`buzz-provider-icon.tsx`（含 `.LICENSE.txt`）列为 `keep_exceptions`。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B1>`。

### 2.2 Channels / IM（B2）

- **入口**：`app/gateway/routers/{channels,channel_connections,integrations,github_webhooks}.py`、`app/gateway/github/**`、`app/channels/**`、`docker/lark-cli-{broker,init}/**`、`.github/workflows/lark-cli-images.yaml`、`scripts/wizard/steps/channels.py`。
- **静态引用**：`app/gateway/app.py:21`（router import）与 `:905-988`（`include_router` 全表）、`app/gateway/routers/__init__.py`（导出表）、`app/gateway/services.py`（channel 相关 run context 投影）、`config/app_config.py`（`channels.*`、`channel_connections.*`、`webhook_dedupe.*` 配置节）。
- **动态引用**：`config.example.yaml` 中 channels/agents/projects 节的字符串模块路径；`docker/docker-compose*.yaml` 的 lark broker/init 服务；`core/i18n` 的 `settings.integrations.lark`；`.github/workflows/lark-cli-images.yaml`。
- **跨树共享依赖**：`deerflow/integrations/lark_cli.py` 被 **KEEP** 文件引用——`community/aio_sandbox/aio_sandbox_provider.py:42-43,1194,2252-2324`（lark 挂载/broker）与 `sandbox/tools.py:2108,2149`（lark 环境注入）。**这两个 KEEP 文件必须与本批同时修改**，删掉 lark 装配但保留 AIO 沙箱与命令工具主路径。这是 B2 最容易漏的一处。
- **DB**：`channel_connections`、`channel_conversations`、`channel_credentials`、`channel_oauth_states`、`webhook_deliveries` 五张表**保留**（见 §3.3），只删 repository/store 实现。
- **替代**：无——IM 接入整体退出产品面；`/api/channels*`、`/api/integrations`、`/api/webhooks/github` 全部 404。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B2>`。

### 2.3 Custom / Managed Agents（B2）

- **入口**：`app/gateway/routers/{agents,subagents,assistants_compat,console}.py`、`tools/builtins/{setup_agent_tool,update_agent_tool}.py`、`config/{agents_api_config,agent_storage_config}.py`、`scripts/migrate_agents_to_db.py`。
- **静态引用**：`app/gateway/authz.py`（agent 权限分支）、`features.py`（agent 能力键）、`agents/lead_agent/agent.py`（custom agent 分支）、`agents/factory.py`（custom agent 选择）、`subagents/registry.py`（managed subagent 来源）、`config/agents_config.py`（`get_agent_store` 三处自由函数）。
- **解除方式**：**同批**删除 store 实现（`persistence/agents/{base,file,sql}.py`、`persistence/managed_subagents/{base,file,sql}.py`）并改写两个包的 `__init__.py` 为"只导出 model"，同时修改 `config/agents_config.py`（去掉依赖 store 的读写自由函数）、`agents/factory.py`、`agents/lead_agent/agent.py`、`subagents/registry.py`。
- **`assistants_compat` 的裁决证据**（结论：可删）：LangGraph SDK 1.5.3 的 `dist/**` 未调用任何 `assistants.*` 方法（只有 `AssistantsClient` 定义，无调用点）；`frontend/src` 从不请求 `/assistants`；`useStream({assistantId:"lead_agent"})`（`core/threads/hooks.ts:1852`）只把 `assistantId` 透传给被覆写的 `client.runs.stream`（`core/api/api-client.ts:459`）；`frontend/tests/e2e/utils/mock-api.ts` 未 mock 任何 `/assistants` 路由，而 chat/sidecar/thread E2E 全绿。
- **替代**：普通 `task` 委派（`deerflow.subagents` runtime + builtin 定义）与 `config.yaml` 内的静态 subagent 定义保留。
- **风险**：`config/agents_config.py` 还被 KEEP 的 lead agent、client、context_compaction 引用，**不能整文件删除**，只能裁剪。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B2>`。

### 2.4 Projects / Documents / Trash / Browser（B2）

- **入口**：`app/gateway/routers/{projects,project_documents,project_thread_files,trash,browser}.py`、`app/gateway/browser_capability.py`、`deerflow/projects/**`、`deerflow/community/browser_automation/**`、`config/projects_config.py`。
- **静态引用**：`app/gateway/deps.py:547`（project repository 依赖）、`routers/threads.py:835,976`（`ProjectNotAssignableError`）、`routers/thread_runs.py`（project 投影）、`thread_data_middleware.py`（project 目录挂载）、`dynamic_context_middleware.py`（project/channel 上下文）、`routers/features.py`（`browser_control` 键）。
- **DB**：`projects`、`project_documents`、`threads.meta.project_id` 表/列保留（§3.3），只删 repository 与写入路径；`metadata.deerflow_project_id` 的写入点全部移除。
- **解除方式**：先删 router 与前端调用方（B1 已完成），再删 runtime 投影，最后删 store。`/api/features` 的 `browser_control` 键在 B1（前端 hook 侧）与 B2（后端键侧）各改一次，清单里两批都登记为 modify——这不是重复，而是跨批一致性要求。
- **替代**：thread ownership、artifact 下载与分析历史完全不受影响。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B2>`。

### 2.5 ACP 与 durable batch（B3）

- **入口**：`deerflow/config/acp_config.py`、`deerflow/config/subagent_batches_config.py`、`deerflow/subagents/{batch_acceptance,batch_runtime,batch_service}.py`、`tools/builtins/batch_task_tool.py`、`tools/builtins/invoke_acp_agent_tool.py`、`app/subagent_batches/**`、`persistence/subagent_batches/{sql,__init__}.py`（model 保留）。
- **静态引用（必须同批改的 KEEP 文件）**：`agents/lead_agent/prompt.py`（ACP 与 durable batch 的工具说明段）、`subagents/runtime.py:15`（`batch_runtime` eager import）、`tools/builtins/__init__.py:2`（`batch_task_tool`/`invoke_acp_agent_tool` eager import）、`tools/tools.py`（工具动态注册分支）。
- **动态引用**：`config.example.yaml` 的 `acp_agents.*` / `subagent_batches.*` 节；`config/app_config.py` 的对应配置节。
- **DB**：`subagent_batches`、`subagent_batch_items` 两张表保留（§3.3）；只删 store 与 `__init__.py` 的导出。
- **替代**：普通 `task` 委派（超时/取消/令牌/回执/循环护栏）完全保留。
- **风险**：`prompt.py` 与 `tools/builtins/__init__.py` 是 KEEP 热路径，改动必须只删条目、不动结构。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B3>`。

### 2.6 Remote sandbox / provisioner / Helm（B3）

- **入口**：`community/{e2b_sandbox,boxlite,opensandbox,tenki}/**`、`docker/provisioner/**`、`deploy/helm/**`、`docker-compose.{cli-auth,openviking}.yaml`。
- **动态引用**：`config.example.yaml` 的 `sandbox.use` 取值与 `sandbox.provisioner_url`；`sandbox/sandbox_provider.py` 的 provider 注册表；`docker/docker-compose.yaml:165`、`docker-compose-dev.yaml:59` 的 provisioner 服务；`.github/workflows/{verify-versions,container,nightly}.yaml` 的 chart/helm 步骤；`scripts/{verify_versions.sh:22-34,bump_version.sh}` 的版本源；`RELEASING.md` 与根 `AGENTS.md` 的版本 lockstep 约定。
- **共享工具的最后引用者**：`sandbox/remote_search.py` 与 `community/url_safety.py` 只有被删 provider 引用（`boxlite/box.py:29`、`e2b_sandbox.py:15`、`opensandbox/sandbox.py:16`、`tenki/sandbox.py:33`；`browser_automation`、`browserless`、`crawl4ai`、`fastcrw`），因此同批删除。**注意：AIO 沙箱的搜索输出解析不走 `remote_search.py`**（`aio_sandbox.py:701` 只是注释），不影响 KEEP 路径。
- **替代**：Local + AIO/Docker 沙箱；`deploy/helm` 整体退出后，版本契约从"三源"（`backend/pyproject.toml`、`frontend/package.json`、`deploy/helm/.../Chart.yaml`）降为"两源"，B4 同步改 `scripts/verify_versions.sh`、`scripts/bump_version.sh`、`RELEASING.md`、`AGENTS.md` 与三个 workflow。**这是本阶段唯一有意缩小的发布契约，必须在报告里明写。**
- **风险**：Kubernetes/Helm 部署方式随本批消失；若将来需要，只能以新批次重建。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B3>`。

### 2.7 Provider zoo（B3）

- **入口**：`community/{tavily,brave,exa,firecrawl,fastcrw,groundroute,serply,sofya,serper,searxng,infoquest,crawl4ai,browserless,tencent_wsa,image_search,ragflow,lightrag}/**`、`models/{claude_provider,openai_codex_provider,mindie_provider,patched_mimo,patched_minimax,patched_stepfun,vllm_provider}.py`、`models/credential_loader.py`、`scripts/export_claude_code_oauth.py`。
- **静态引用（必须同批改的 KEEP 文件）**：`models/factory.py:245`（**无条件** import `CodexChatModel`）、`:307-309`（MindIE `__name__` 特判）；`agents/middlewares/{token_usage_middleware.py:172,tool_result_sanitization_middleware.py:61}` 的 `image_search` 名；`backend/docs/{CONFIGURATION,GUARDRAILS,TODO}.md`、`deerflow/models/AGENTS.md`、`deerflow/tools/AGENTS.md`、`deerflow/agents/middlewares/AGENTS.md`；`scripts/doctor.py:486-510,612,768`、`scripts/wizard/{providers,writer}.py:84`；前端 `core/tools/utils.ts:16`、`core/messages/usage-model.ts:282`、`components/workspace/messages/message-group.tsx:581,745`。
- **config 键**：`models[]` 中的 codex/claude_code/mindie/mimo/minimax/stepfun/vllm 条目；`tools:` 中 `image_search` 与 `knowledge_search` 条目；`memory.backend` 的 honcho/mem0/openviking 取值。
- **依赖**：B4 从 Python 声明与 `uv.lock` 移除无剩余 importer 的 `agent-client-protocol`、`boxlite`、`e2b-code-interpreter`、`exa-py`、`firecrawl-py`、`kubernetes`、`langchain-openviking`、`opensandbox`、`tavily-python`、`tenki`；`honcho`、`mem0ai`、`vllm` 与 `langchain-mistralai` 在 B4 起点已不在依赖声明或锁文件中。前端仅移除无 importer 的 `nuxt-og-image`，保留被当前组件使用的动画、轮播、特效依赖。
- **`credential_loader.py` 的最后引用者**：只有 `claude_provider.py`、`openai_codex_provider.py` 与三个被删测试，同批删除安全。
- **替代**：Web Search = DuckDuckGo（`deerflow.community.ddg_search`）、Web Fetch = Jina AI Reader（`deerflow.community.jina_ai`）；模型 = OpenAI-compatible + DeepSeek。
- **能力损失（必须明写）**：`RAGFlow` 与 `LightRAG` 删除意味着**整个 `knowledge_search` RAG 知识检索能力消失**；`image_search` 消失意味着图像搜索能力消失；多个 search 后端消失意味着去中心化/自建搜索（SearXNG）与商业搜索（Brave/Serper/Sofya/Exa/InfoQuest/TencentWSA）全部退出。
- **风险**：删除 `url_safety.py` 后，**本地不再有任何 SSRF 防护模块**；剩余 web fetch（Jina）走外部服务，安全边界从"本地 URL 校验"变为"仅信任目标服务"。此风险必须写进产品文档。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B3>`。

### 2.8 Memory providers（B3）

- **入口**：`agents/memory/backends/{honcho,mem0,openviking}/**`、`docker/docker-compose.openviking.yaml`、`docs/OPENVIKING.md`、`docs/plans/OPENVIKING_HTTP_MEMORY_INTEGRATION.md`。
- **解除方式**：`memory.backend` 取值收敛为 `deermem` / `noop`；config 校验与 wizard 选项同步删除；`deerflow.mcp` 与 OpenViking 的集成点同批移除。
- **替代**：DeerMem（含 `select_facts_for_capacity`）与 Noop 后端、业务偏好主链（`user/preferences.py`）保留。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B3>`。

### 2.9 Skill platform / media（B4）

- **入口**：`deerflow/skills/review/**`（9 模块）、`tools/builtins/review_skill_package_tool.py`、`contracts/skill_review/**`（4 个 schema）、`skills/public/{skill-reviewer,skill-creator,find-skills,...}/**`、`scripts/{review_changed_public_skills,skill_review_waivers}.py`、`.github/skill-review-waivers.v1.json`、`.github/workflows/skill-review-ci.yml`、`tests/skills/**`、`.github/workflows/chart.yaml` 与三个 `scripts/check_*` 脚本。
- **静态引用（必须同批改的 KEEP 文件）**：`deerflow/skills/tool_policy.py`（`review_skill_package` 策略条目）、`tools/builtins/__init__.py`（导出）、`deerflow/skills/AGENTS.md`、根 `AGENTS.md`（Skill quality review note 段）、`backend/AGENTS.md`。
- **必须保留的相邻能力**：`deerflow/skills/{loader,parser,permissions,projection,security_scanner,security_static_scanner,skillscan}/**` 是**安装期**安全门禁，由 KEEP 的 `/api/skills` 与 `skills/installer.py` 调用，**不随 review 平台或 Agent self-evolution 删除**。Agent 运行期 `tools/skill_manage_tool.py` 和 lead prompt 的自编辑入口另行 DELETE；管理员/用户隔离、安装、启停、读取与手工编辑的 `/api/skills` 契约继续保留。`skill_security` 配置继续控制 LLM moderation 与 fail-closed 策略，`skill_scan.enabled` 只控制既有确定性扫描。
- **CI 影响**：`.github/workflows/skill-review-ci.yml` 与其 waiver 清单删除后，公开技能的评审门禁消失——这与"只保留 loader/policy/activation 与业务分析技能"的 KEEP 契约一致。
- **替代**：KEEP 技能 = `business-analysis`、`data-analysis`、`chart-visualization`、`consulting-analysis`、`bootstrap`；`/api/skills` 的管理员/用户隔离、安装/启停/读取/手工编辑契约不变。旧 `skill_evolution.moderation_model_name` 与 `security_fail_closed` 逐字段迁移到 `skill_security`；旧 `enabled` 不迁移。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B4>`。

### 2.10 Dependencies / config / tests / docs（B4 + B5）

- **依赖**：只在 B3 删除最后一个 importer 之后，从 `backend/pyproject.toml`、`backend/packages/harness/pyproject.toml`、`frontend/package.json` 移除，并同步 `uv.lock`、`pnpm-lock.yaml`；门禁 `uv lock --check` + `pnpm install --frozen-lockfile`。
- **配置键**：`config.example.yaml`、`extensions_config.example.json`、`backend/packages/harness/deerflow/config/app_config.py`；配置结构变化必须同步 `config_version` 与 `scripts/check_config_version.sh`（该脚本在 B4 删除，故 `config_version` 校验改为在 B5 用 wizard/doctor 复验）。
- **测试**：删除判据是"被测模块被删"，不是文件数。混合覆盖的测试**改而不删**（清单 `modify_files` 已逐条列出，例如 `test_web_search_time_range.py` 只删商业 provider 用例、保留 KEEP 的 DDG `time_range` 覆盖；`test_token_budget_middleware.py`/`test_tool_call_metadata.py` 把 claude_provider 换成 KEEP 的 OpenAI-compatible 模型）。
- **文档/CI**：README/AGENTS/backend docs/CHANGELOG 同步；CI job 只在对应脚本删除后移除。
- **回滚**：随该批次提交，依赖链逆序回滚（见 §1）；`git revert <B4>`、`git revert <B5>`。

## 3. 引用证明与特别裁决

每条裁决只给一个结论（不做菜单），依据是仓库内的可复现证据。

### 3.1 Web Search / Fetch 只保留一条实现（证据否决了 Tavily 候选）

架构文档 §2 把默认候选写成 Tavily，但真实配置与依赖流向给出相反结论，故**保留 `community/ddg_search`（web_search）+ `community/jina_ai`（web_fetch）**：

- `config.example.yaml:806-809` 中未注释的 web_search 指向 `deerflow.community.ddg_search.tools:web_search_tool`；`:1063-1066` 未注释的 web_fetch 指向 `deerflow.community.jina_ai.tools:web_fetch_tool`；其余 provider 全部处于注释状态。
- `tools/tools.py:105,113` 只按配置列表经 `resolve_variable(cfg.use, BaseTool)` 装载工具，没有运行时 provider 注册表——即"配置里没写就不存在"。
- `scripts/wizard` 的 provider 列表把 `ddg` 与 `jina_ai` 列在首位且无需 API key；`scripts/doctor.py:486-487` 报告的默认值与之一致。

结论：Tavily/Exa/Firecrawl/fastCRW/GroundRoute/Sofya/Brave/Serper/Serply/SearXNG/InfoQuest/TencentWSA/Crawl4AI/Browserless 全部退出；`image_search`、`knowledge_search` 一并退出（见 §3.2、§3.6）。

### 3.2 `community/image_search` 删除（覆盖 platform 审计的 KEEP 建议）

`image_search` 的唯一消费者是图像生成类技能与 `brave`/`serper`/`infoquest` 的 image 工具，而这些实现与本阶段删除的技能同批消失；KEEP 契约只命名一条 Web Search/Fetch 路径。故按后端审计结论删除，并同步修改 `scripts/doctor.py`、`scripts/wizard/writer.py:84`、`config.example.yaml`、两个 middleware 的工具名分支与前端三处工具名分支。

### 3.3 历史 migration 与 ORM model 一律 KEEP

`backend/tests/test_persistence_bootstrap.py:520` 断言 `create_all` 的表集合与 `alembic upgrade base→head` 的表集合完全一致。26 个 revision 与全部 ORM model 都保留，只删每个域的 store 实现（`sql.py`/`file.py`/`base.py`）并把 `__init__.py` 改写为只导出 model。删除表或 revision 需要"是否允许全新 squash migration"的产品决策，超出 Phase 5A 授权 → 见 §5 BLOCKED。

### 3.4 Helm 与版本契约

`deploy/helm/**` 整体删除，版本源从三源降为两源；同批修改 `scripts/verify_versions.sh`、`scripts/bump_version.sh`、`RELEASING.md`、`AGENTS.md`、`.github/workflows/{verify-versions,container,nightly}.yaml`。这是有意的契约收缩，不是遗漏。

### 3.5 `mcp_tasks` KEEP

MCP 长任务运行时（`McpTaskService` + `mcp_tasks` 表 + 租约恢复/取消栅栏/投递幂等）属于 KEEP 的 MCP 契约，十个候选域无一覆盖它，故不删。

### 3.6 `RAGFlow` + `LightRAG` 删除 = RAG 知识检索能力消失

`knowledge_search` 工具组的两个实现都在删除集合内，删除后 `knowledge` 工具组整体不存在。这是能力损失而非重构，必须进入产品说明与验收记录。

### 3.7 安全测试不得为凑数而删

清单自洽脚本对 `test_analytics_*`、`test_harness_boundary`、`test_semantic_authorizer`、`test_sql_policy`、`test_authorize_prepared_query` 等 Phase 0–4 安全测试做硬校验：出现在任何删除集合里即报错。

## 4. 规模收敛：目标不可达

### 4.1 实测对账

| 指标 | baseline | 删除 | 保留 | 目标区间 | 硬上限 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| tracked 文件 | 3073 | 783 | **2290** | 850–1050 | 1200 | 高出硬上限 1090 |
| 生产源码 | 1399 | 339 | **1060** | 450–650 | — | 高出上限 410 |
| 测试文件 | 1078 | 184 | **894** | 250–350 | — | 高出上限 544 |
| 有效文本 LOC | 717429 | 169533 | **547896** | 140k–220k | — | 高出上限 327896 |

五批删除量：B1 263、B2 171、B3 185、B4 103、B5 61（tracked）。

### 4.2 不可删成本（按域，互斥且合计等于保留量）

| 域 | tracked | text-LOC | 为什么不能再删 |
| --- | --- | --- | --- |
| `backend/tests` | 655 | 272052 | Phase 0–4 安全与运行期回归的唯一载体 |
| Harness 其余（lead runtime、middleware、runtime、subagents、sandbox、mcp、skills loader、tools、models factory、config、utils） | 480 | 107336 | KEEP 契约的产品能力本体 |
| `frontend/src` | 406 | 68051 | 分析工作台、chat 主链、artifact、设置、i18n |
| `frontend/tests` | 236 | 50852 | KEEP 路由的 unit/dom/e2e 覆盖 |
| `docs` + `backend/docs` | 103 | 0 | 阶段文档、验收契约、模块指南 |
| `deerflow/persistence` | 81 | 7798 | 26 个 Alembic revision + ORM model 与 `create_all` 集合一致 |
| 其余（gateway、analytics、scripts、docker、deploy、contracts、skills、examples、.agent、CI） | 410 | 49605 | KEEP 主链、注册表、运维脚本与维护者技能 |
| **合计** | **2290** | **547896** | — |

**结论：Phase 0 设定的 850–1050 / 450–650 / 250–350 / 140k–220k 在 KEEP 契约不变的前提下不可达。**
本清单给出的是"按域审计后能删的最大集合"（保守最小值），差额不是"没删干净"，而是 KEEP 契约定义的产品面本身。
若要在数字上达标，只能修改 KEEP 契约（例如放弃 Analytics 安全测试、放弃 Harness 分层或放弃前端工作台），那是产品决策，不属于 Phase 5A 授权范围。

## 5. BLOCKED（Phase 5A 无法证明，需后续批次或决策）

| 项 | 缺什么证据 |
| --- | --- |
| `frontend/next.config.js` 的 nextra 包装、`src/mdx-components.ts`、`src/typings/md.d.ts` 能否随零 MDX 路由一起删除 | 需要真实 `pnpm build`；Phase 5A 只做静态审计，故列为 BLOCKED→KEEP，B5 视构建结果再裁决 |
| 删除任何表或任何 Alembic revision | 需要"是否允许全新 squash migration 且不保留旧数据"的产品决策（§3.3） |
| `frontend/tests/e2e/utils/mock-api.ts` 中的真正死分支 | 需要实跑 Playwright 才能确认哪些 `page.route` 已无 spec 使用；B1 先修剪、B5 收尾 |
| `/api/features` 的 `browser_control` 键与 `useBrowserControlEnabled` | 跨 B1（前端 hook）与 B2（后端键）两批，清单在两批都登记为 modify，需靠 focused 门禁确认无中间态残留 |
| `.agent/skills/**`（18 个维护者技能） | 不属于十个候选域中的任何一个，也不属于产品运行时；清单按 KEEP 处理并在此记录 |

## 6. 残余风险与收敛门禁

1. **SSRF 防护净损失**：`community/url_safety.py` 删除后没有本地 URL 校验模块（§2.7），必须写进安全说明。
2. **发布契约收缩**：Helm/Chart 与三源版本校验消失（§3.4），CI 的 chart 与 nightly 步骤同步移除。
3. **字符串与文档层面的孤儿引用**：Python import 已被最后引用者证明清零，但 `config.yaml use:` 字符串、`registry` 名、i18n 命名空间、文档正文仍需 B5 用 `rg` 逐项扫（命令见 `phase-05-verification-matrix.md` §2 B5）。
4. **测试清理边界**：混合覆盖测试"改而不删"的 20 条已在清单 `modify_files` 里逐条写明改什么；B5 全量测试必须绿。
5. **Phase 5B 不得跳批**：B1→B5 的依赖方向不可交换（§1），每批结束都必须满足 `phase-05-verification-matrix.md` §3 的十一条不变量。
