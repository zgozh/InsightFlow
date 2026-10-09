# 2026-10-09 Scheduler Recovery 最终验收

## 结果

AS12 的 PostgreSQL→Gateway 受控重启持久化检查通过：现有成功分析的 history/checkpoint/report/query artifact/events 共 19 项与重启前一致；重启后 Gateway healthy，前端仍能查看原分析的 8 个 stage 和 1 张报告卡。checkpoint SHA-256 为 `49a593fad2fd4cd3924c855475985872b057b1df3cfa82f647bdef508a2148dc`，report artifact 为 `e5e46a75bb39df4c5774fcbfc8c3141025cd341fcc61341cb7db8eb2ac59e488`，query artifacts 为 `d9628f67a773a2efca8f079f3c5ee386eb435f3e95bb6d1e7a42fe41cba9e6a3`，events 为 `f3e8e89b3d567929e320c7b4a4d67b7e65076054536e6064e0b73c38df20aef3`。

AS11 的旧 run 未通过。mounted runtime config 的 scheduler 已启用；更新前后配置副本保存在 `.reviews/final-postgres-runtime-20261008/final-integration-current/`。本次只把 `roles.py` COPY 到 Gateway 镜像，base 为 `31e27efc80a0…`，新镜像 ID 为 `8620d005f186…`；Gateway healthy，Frontend、Nginx、Redis 容器未重建。旧 Gateway 镜像另有本地 rollback tag。

新的自动任务首次以 15 秒延迟创建时收到 HTTP 422。旧 helper 没有保留响应详情；Gateway 校验要求 once 任务至少提前 `min_once_delay_seconds`，当前未显式设置时默认 60 秒。只读任务清单确认这次被拒请求没有创建 task。随后使用独立 claim 创建唯一有效任务，`schedule_type=once`、`context_mode=reuse_thread`，delay 为 90 秒；task/thread/occurrence/run 原始 ID 保存在私有 context。仅有 1 个 scheduled occurrence、1 次 scheduler attempt，run 终态 `error`，task 终态 `failed`，没有重复触发。

新 run 的 Data stage 为 `succeeded/ok`，Writer stage 为 `succeeded/ok`。Reviewer 唯一一次拒绝，stage 为 `blocked/review_rejected`，闭合 `reason_code=evidence_mismatch`；Publish 未通过，workflow 终态为 `failed/unavailable`。Owner report 数量为 0，因此这次不作为已发布报告验收。该 run 没有暴露数字校验 reason；25 分钟日志窗口内 `analysis_data_parser_rejected.numeric_verification` 固定枚举计数为 0。此结果证明 Data 与 Writer 走到成功，但 reviewer 对结构化输入给出证据不匹配，具体应由 Principal 独立审查 reviewer 输入证据范围；不重发模型任务。

定点验证命令 `uv run pytest tests/test_run_worker_delivery.py::test_delivery_event_emitted_when_cancelled_waiting_for_prior_finalization tests/test_gateway_services.py::test_apply_checkpoint_returns_only_terminal_owner_thread_producer tests/test_analytics_agent_evidence_bridge.py::test_durable_collector_restores_current_and_checkpoint_producer_evidence_in_request_order -q` 通过，结果 `7 passed in 8.68s`。这组测试覆盖 worker 取消投递、owner/thread/terminal producer 边界和 collector 的顺序恢复，但 checkpoint producer 与 collector 使用测试替身；没有完成实际 PostgreSQL checkpointer 下的显式 producer-scope 复用，也没有发起 live cancellation。AS08 live cancel/checkpoint 仍 pending。AS12 的 restart hash 一致只证明已有成功状态持久化，不证明显式续跑 producer scope。`ask_clarification` 工具计数未确认。

为隔离旧 thread 的多轮工具历史，另创建一个全新 `kind=analysis` thread；创建前确认 run history 与 report history 均为空。唯一 90 秒 once/reuse_thread 任务自动产生 1 个 occurrence、1 次 scheduler attempt，run=`error`、task=`failed`，无 report。首轮 SQL、authorization、execution、Data、Writer 均成功；Reviewer 两次结构化拒绝，reason 顺序为 `unsupported_claim`、`evidence_mismatch`。同一 run 后续工具循环出现 authorization=`policy_denied`、SQL/Data=`attempt_limit`，最终 workflow=`unavailable`。消息中发现 3 个工具名且未发现 `ask_clarification`；未将此失败记录为正例，也未再发起任务。旧 thread 的 reviewer 拒绝样例仍保留。

安全终态摘要和私有 ID 位于 `.reviews/final-postgres-runtime-20261008/final-integration-current/`。本记录不含 scheduled 错误正文、认证信息或原始内部 ID。
