### Tool System (`packages/harness/deerflow/tools/`)

`conversation.py` supplies the optional `read_conversation` tool. Ordinary lead
assembly opts in only with a host reader; default, bootstrap, embedded and
subagent assembly withhold it. The tool requires the worker-owned
`__conversation_reader` capability and rejects subagents. Hosts enforce the
current run's explicit references and user permissions. Do not import Gateway
routers into the harness or recover this capability from persisted messages.
Reads use live visible history; expiry/deletion does not erase destination copies.
The Gateway sizes pages to the `CONVERSATION_TOOL_NAME` tool-output budget so
results stay inline. Cut messages carry a `message_seq`/`offset` continuation that
the same host reader serves; keep reading guidance separate from permission enforcement.

`get_available_tools(groups, include_mcp, model_name, subagent_enabled)` assembles:
1. **Config-defined tools** - Resolved from `config.yaml` via `resolve_variable()`
2. **MCP tools** - From enabled MCP servers (lazy initialized, cached with resolved-path + content-signature invalidation)
3. **Built-in tools**:
   - `present_files` - Make output files visible to user (only `/mnt/user-data/outputs`); virtual paths use `resolve_runtime_user_id(runtime)` so validation resolves the same user-scoped outputs directory established by `ThreadDataMiddleware`
   - `ask_clarification` - Request clarification (intercepted by ClarificationMiddleware, which preserves text fallback and adds `artifact.human_input` for Web UI Human Input Cards). Beyond free text and single choice, the request-side v2 protocol supports `fields` (structured form card collecting several values at once; field types: text/textarea/number/select/multi_select/checkbox/date, validated and normalized server-side in the middleware — invalid entries are dropped, unknown types degrade to `text`; a standalone multi-select question is a one-field form). Replies stay on the v1 response protocol (`text`/`option`): the form card submits a readable text summary
   - `view_image` - Read image bytes for vision-capable models; live sandbox bytes win for the same sandbox generation, replacement-sandbox recovery uses only SHA-256-verified synchronized host bytes, and async tool invocation drains blocking reads before cancellation may release the sandbox lease
4. **Subagent tool** (if enabled):
   - `task` - Delegate to subagent (`prompt`, `subagent_type`, optional `acceptance_criteria`, and an optional model-visible `description` used only as a short progress label). Execution never depends on `description`; lifecycle display falls back to `prompt` when a provider omits it. Subagent reports are self-reports: the docstring directs the lead to expect `[rN]` receipt citations and verifiable handles while `verification.receipts_enabled` (and explicitly qualifies that disabled receipts mean no citations and no citation verdict), to read the delegation ledger's citation cross-check as execution evidence only, and to attach `acceptance_criteria` for objectively checkable outcomes (canonical forms `file:<path> exists|non-empty`, `file_written:<path>`, `tests_passed:<command>`); criteria are handed to the executor and appended to the subagent's task message as untrusted data (see `subagents/report_contract.py`).
     Polling safety timeouts carry the latest published tool receipts into the terminal task metadata before requesting background cancellation.

   - Direct `create_deerflow_agent` integrations receive cloned tools bound to their explicit `SubagentRuntime`. The bound `task` forwards that runtime's exact execution controller and optional caller-owned `AppConfig` into registry/model/tool resolution and `SubagentExecutor`. Keep the original tool name/schema unchanged so model contracts and user-tool deduplication remain stable.

受控分析分支通过 `analysis_mode=True` 绕过普通工具装配，只按固定的 `name`、`group`、`use` 三元组加载 `inspect_business_catalog`、`query_business_data` 与 `write_analysis_report`。普通工具装配必须同时排除 writer 名称和其固定来源，避免配置别名把它带入普通聊天。不得在分析分支读取 MCP 配置/缓存、动态工具目录或扩展来源。Lead assembly 必须把同一最终工具集合交给模型 schema 与图执行，并排除 deferred discovery、task、普通中间件等可能注入新工具的路径。writer 的模型 schema 只有标题、Markdown 正文和 evidence ID；执行时还必须持有 Gateway 注入的本 run 能力，不能通过一般配置或模型自报身份获得文件写权限。`analysis_mode` 不是授权凭据：只有 Gateway 从持久化线程标记生成、且清除客户端同名输入后的运行 context 才可表达可信模式；在 `analysis_mode_unavailable` 门禁解除前，合成构图测试不代表分析入口已开放。

The ordinary `task` boundary carries one narrow parent-loop middleware recorder into the isolated subagent runtime under separate loop-detection, tool-promotion, and tool-progress keys. It schedules only `record_middleware` calls back onto the loop that owns `RunJournal`, keeps an execution-local atomic promotion claim so parallel searches do not double-report one new schema, is fenced and drained once before `task` returns, and never exposes the journal or event store to the child loop.

Scheduled-task runtime note:
- Scheduled background runs set `context.non_interactive=true` and therefore exclude `ask_clarification` from the lead-agent tool list. This keeps scheduler-triggered runs from stalling on human confirmation mid-execution. `non_interactive` is an internal-only context key: it is merged from `body.context` only when the request authenticated as the process-internal user (the scheduler path), never from arbitrary HTTP clients.

Durable MCP task-management tools are added only while the process-local task submitter is installed. They expose bounded local task fields, including whether cancellation was requested, but never the remote handle. Cancellation records that request durably and returns immediately; the background service owns the remote call and retries. These remain ordinary business tools under an active skill's `allowed-tools` policy and must be declared explicitly.

**Community tools** (`packages/harness/deerflow/community/`): optional integrations, each in its own subpackage and wired through `config.yaml`. Documented examples:
- `ddg_search/` - Web search（DuckDuckGo，保留的唯一 web_search 实现）
- `jina_ai/` - Web fetch via Jina reader API with readability extraction
- `aio_sandbox/` - Docker-based isolation (`AioSandboxProvider`)

Phase 5 之后本目录只剩 `ddg_search`（web_search）、`jina_ai`（web_fetch）与 `aio_sandbox`（Docker 沙箱）；其余 provider 与远程沙箱实现已删除。
