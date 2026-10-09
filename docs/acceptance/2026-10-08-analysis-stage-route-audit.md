# AS09 阶段事件接线有限取证

范围：只读既有 worker/journal/SSE/replay 与前端消费路径；未查看另一 worker 的角色集成改动，未运行检查。

## 现有路径与合同

- `aemit_custom_event` 先写 `StreamWriter`，再 best-effort 调用 `adispatch_custom_event(name, payload)`；`name` 取非空 `payload.type`，callback data 保留原 payload（`backend/packages/harness/deerflow/utils/custom_events.py:17-22,45-56`）。
- Worker 的 `custom` stream mode 经 `bridge.publish(run_id, "custom", payload)` 原样进入 SSE；SSE 帧事件名为 `custom`，payload 在 `data`（`backend/packages/harness/deerflow/runtime/runs/worker.py:1328-1360,3156-3188`；`backend/app/gateway/services.py:212-225,2241-2245`）。
- 前端 `useThreadStream.onCustomEvent(event)` 读取 `event.type`；现有 `task_*` 事件更新子任务状态/步骤（`frontend/src/core/threads/hooks.ts:1943-2000`）。因此浏览器合同是 `event: custom`、`data.type: <业务名>`，不是 SSE event 名直接改为 `analysis_stage`。
- Live SSE 的 `Last-Event-ID` 重放来自有界 `StreamBridge` 缓冲区，过早游标产生 gap；前端 gap 后清游标、重载持久 thread state，再从 retained tail 续订（`backend/app/gateway/services.py:2193-2245`；`frontend/src/core/api/api-client.ts:379-419`）。Gap 不代表 run 结束或取消。
- `RunJournal` 写入 run/LLM/tool 等 `run_events`；没有通用 custom callback 持久化。Worker 的 `_SubagentEventBuffer` 只接收可转成 `subagent.*` 的子代理事件，其他 custom chunk 忽略（`backend/packages/harness/deerflow/runtime/journal.py:354-404,408-445`；`backend/packages/harness/deerflow/runtime/runs/worker.py:755-800`）。
- 持久 `GET /threads/{thread_id}/runs/{run_id}/events` 读取 `RunEventStore`，按 `after_seq` 分页；其 `seq` 在 thread 内单调递增。它与 SSE 的 per-run bridge event ID 是两条游标（`backend/app/gateway/routers/thread_runs.py:1715-1750`；`backend/packages/harness/deerflow/runtime/events/store/base.py:46-79`）。当前只有子代理步骤有 live-to-persisted 映射及回填（`frontend/src/core/tasks/steps.ts:116-147`）。
- 通用 custom payload 当前没有应用级 `seq`/去重键。可复用的子任务路径用 `task_id` 聚合、`message_index` 排序并在 live/backfill 合并时去重（`frontend/src/core/tasks/lifecycle.ts:19-56`；`frontend/src/core/tasks/steps.ts:150-169`）。消息上的 `deerflow_seq` 是持久消息顺序，不是 stage 游标（`frontend/src/core/threads/message-order.ts:34-72`）。
- 取消落点是 ChatPage `thread.stop()` → Gateway `POST /runs/{run_id}/cancel` → `RunManager.cancel`；worker 异常写终态 error 并发布 SSE `error`。前端 `onError` 清理临时消息并刷新历史，`onFinish` 刷新停止态缓存（`frontend/src/components/workspace/chats/chat-page.tsx:249-251`；`backend/app/gateway/routers/thread_runs.py:1159-1216`；`backend/packages/harness/deerflow/runtime/runs/worker.py:1524-1547`；`frontend/src/core/threads/hooks.ts:2002-2033`）。

## 可复用 UI 与最小 owner

- 现有可复用状态/UI 是子任务专用：`SubtaskContext`、`Subtask` 的 `in_progress|completed|failed` 与 `SubtaskCard`/`ChainOfThought` 时间线（`frontend/src/core/tasks/context.tsx:13-40`；`frontend/src/core/tasks/types.ts:7-25`；`frontend/src/components/workspace/messages/subtask-card.tsx:46-112`）。它有 prompt/result/模型/步骤语义，不是通用分析阶段状态。
- 分析路由复用 `ChatPage mode="analysis"`，并由该页调用通用 `useThreadStream`（`frontend/src/app/workspace/analysis/[thread_id]/page.tsx:41-66`；`frontend/src/components/workspace/chats/chat-page.tsx:71-79,118-132`）。若阶段仅作当前分析页的临时状态，最小前端 owner 是 `core/analytics/types.ts` + `schemas.ts`（闭合类型/strict 校验）、`core/threads/hooks.ts`（接收/校验）与 `components/workspace/chats/chat-page.tsx`（analysis-only 状态/渲染），以及 `core/i18n/locales/analytics.zh-CN.ts` / `analytics.en-US.ts` 文案（现有 schema 模式：`types.ts:26-35`、`schemas.ts:223-245`）。`ChatProviders` 当前只包子任务 provider（`frontend/src/components/workspace/chats/chat-providers.tsx:5-14`）；不要把阶段塞进子任务状态。
- 若要求刷新后历史回放，必须另接持久 `run_events` 写入与 `GET /events` 回填；现有 custom SSE replay 本身只覆盖 bridge 保留窗口，不提供永久历史。

## 有限契约候选

- `data = {type:"analysis_stage", version:1, run_id, seq, stage, status, counts?, risk?, duration_ms?, code?, evidence_ids?}`；`seq` 是 payload 内 per-run 单调序号，不能隐式借用 SSE event ID 或 thread-global event-store seq。
- `stage` 闭合集合：`sql | data | writer | reviewer | authorization | execution | publish`。`status` 闭合集合：`running | succeeded | failed | blocked | skipped | cancelled`。
- 仅允许有界整数 counts、受限枚举 risk、非负 duration、有限 code、受界 evidence ID 列表。禁止 SQL、结果行、secret/DSN、plan token、CoT、自由文本错误。
- `RunJournal` 可提供 run 级 tokens 与 lead/subagent/middleware 聚合及按模型聚合，但没有 stage 维度；实际 stage token usage 来源 **unknown**，不得从总量拆算（`backend/packages/harness/deerflow/runtime/journal.py:913-942,1327-1341`；`backend/app/gateway/routers/thread_runs.py:1775-1787`）。
