# Analysis checkpoint evidence 续跑定点审查

## 结论

发现 ADR0005 的 checkpoint 续跑证据绑定缺口：analysis run 从另一个 run 的 checkpoint 续跑时，报告工具无法解析 checkpoint 中旧的成功查询 evidence。当前行为是整体返回 `analysis_evidence_unavailable`，属于安全拒绝，但不满足 ADR0005“后续 checkpoint 续跑通过服务器验证的来源 run 关系重建工作集”的承诺。以下仅基于生产源码；没有改生产代码、运行测试、构建、启动容器或调用模型。

## 可证明的代码事实

- `backend/app/gateway/services.py::start_run` 先校验线程 owner，再将 analysis 外部输入规整为新输入；显式 `command.resume` 走单独分支。`apply_checkpoint_to_run_config()` 对请求中的 checkpoint selector 按目标 `thread_id`、namespace、checkpoint ID 从 checkpointer 读取；缺失时拒绝，但只把 selector 放进新 run config，没有把已验证 checkpoint 的 metadata/source 传给 evidence collector。
- 每个 analysis admission 都在 `backend/app/gateway/services.py` 用当前 `record.run_id` 签发 report writer、artifact capability 和 `DurableAnalysisRunEvidenceCollector`。`backend/app/analytics/agent/reports.py` 要求 collector 匹配受信 runtime 的 `(principal, thread, run)`，然后用当前 `run_id` 调 `resolve_successful_queries_durable()`。
- `backend/app/analytics/agent/evidence_bridge.py::DurableAnalysisRunEvidenceCollector` 将当前 `run_id` 传给 `AnalysisEvidenceRepository.get_many()`，并逐条校验 DTO 身份、evidence ID、固定 artifact path 和 artifact 字节。`backend/app/analytics/infrastructure/persistence/evidence.py::SqlAnalysisEvidenceRepository.get_many()` 的 SQL 读取条件是 `(principal_id, thread_id, run_id, evidence_id)`，缺少任一记录即整体拒绝。因此 checkpoint 里的旧 ToolMessage 即使保留成功查询结果和 evidence ID，也不能在新 run 的 scope 下命中原记录。
- Harness `backend/packages/harness/deerflow/runtime/runs/worker.py` 当前只向 checkpoint config metadata 注入 agent name 和 trace ID，没有写入当前 `record.run_id`。`backend/app/gateway/services.py::build_run_config()` 会复制 `request_config` 的其他字段，并合并请求 metadata；因此现存 `metadata["run_id"]` 若出现，不能证明是服务端 run ID。`run_message_ids` 由 `backend/app/gateway/routers/threads.py` 的 thread history 读取路径异步补写，只是 AI message → run ID 的 history 辅助索引，不是 checkpoint producer 身份或 evidence 来源的信任根。
- 普通新输入仍只用当前 run collector；显式 checkpoint selector 才有可供恢复来源的服务端验证边界。不能把客户端 `source_run_id` 或任意 evidence ID 当作恢复授权。

## 最小方案

1. 在 `backend/packages/harness/deerflow/runtime/runs/worker.py` 的 checkpoint `RunnableConfig.metadata` stamping 处写入保留的 server-owned producer 字段（例如 `deerflow_analysis_run_id = record.run_id`），覆盖任何请求同名值。不要将客户端 metadata 作为来源证明。
2. 在 `backend/app/gateway/services.py::apply_checkpoint_to_run_config()` 已读取并确认 checkpoint 属于 path thread 后，从该 tuple 的 metadata 提取 producer ID；沿用 `backend/app/gateway/routers/thread_runs.py::_require_successful_source_run()` 的 owner-scoped run lookup、thread 和 success 校验。仅显式选定且通过校验的 checkpoint 才向本次 collector 传递有限来源；普通新提问不继承旧 run 来源。
3. 扩展 `backend/app/analytics/agent/evidence_bridge.py::DurableAnalysisRunEvidenceCollector` 保留当前 run 的新查询能力，并只允许当前 run 与已验证 checkpoint producer 这组有限来源。逐条从对应 `(principal, thread, source_run, evidence_id)` 读取；复用 `backend/app/analytics/infrastructure/persistence/evidence.py::SqlAnalysisEvidenceRepository.get_many()` 的 scope 读取、成功结果校验，以及 `backend/app/gateway/analysis_query_artifacts.py::AnalysisQueryArtifactCapability.verify()` 的固定 artifact 核验。artifact capability 必须按记录的 source run 派生路径。任一身份、来源、记录或 artifact 校验失败，整份报告返回稳定的 `analysis_evidence_unavailable`。

未带可信 producer 字段的旧 checkpoint 可以继续正常续跑，但不能恢复旧 evidence；报告若引用旧 evidence 必须失败关闭，用户可在当前 run 重新查询。不能回退到客户端 source ID、扫描任意 run 或信任 `run_message_ids`。单个 producer ID 只证明该 checkpoint 的写入 run；若未来要恢复同一 checkpoint 中更早多个 run 的 evidence，必须另有逐项可验证的来源关系，不能把所有历史 evidence 归给最新 producer。

## 回归边界与验证范围

- 显式同 owner/thread checkpoint 带服务端 producer ID，source run 成功且 evidence 与固定 artifact 完整：新 run 可解析。
- 客户端伪造同名 metadata / `source_run_id`，或 source run 属于其他 owner/thread、状态非成功：均不得读取该来源。
- 旧 checkpoint 缺少或包含无效 producer ID：checkpoint 仍可续跑，引用旧 evidence 时整体失败关闭。
- 普通新提问不获得旧 run allowlist；当前 run 新查询 evidence 仍可被同 run 报告使用。
- 来源集合中存在缺失记录、重复或跨来源冲突 ID、损坏 payload 或缺失/篡改 artifact：不返回部分证据。

预期按 V2 验证：定点覆盖 `apply_checkpoint_to_run_config` 的 thread/source 边界、server metadata 覆盖、collector 来源 allowlist，以及 repository + artifact 的逐份/整体失败行为；运行受影响的后端定点测试和相关 Ruff 检查。持久化读取需覆盖 PostgreSQL 路径；最终发布要求的真实 PostgreSQL 验收仍是发布门禁，本审查没有运行它。纯审查记录做 readback/diff 检查即可。
