# AS09 分析阶段事件服务端切片

## 行为

Gateway 为每个受控分析 run 发行绑定 principal、thread、run 与既有事件存储的阶段 emitter，并通过现有 `AnalysisRolesCapability` 传给 query/report role。emitter 生成受 `analysis-stage.v1.json` 约束的有限 metadata；写入既有 RunEventStore 时使用 `event_type="analysis.stage"`、`category="analysis"`、空 `content`，完整 payload 放入 `metadata`。数据库写入成功后才发送同一 payload 的现有 `custom` live event。metadata 内的 `seq` 按 run 递增，与 store 的 thread 全局游标分开。

query、report 的阶段围绕真实 catalog、SQL、授权、执行、data、writer、reviewer 与 publish 操作发出。整数校验排除 bool；额外字段、原始 SQL/结果行和自由文本错误不会进入阶段记录。运行失败、blocked、取消与成功分别映射到实际终态；worker 的终态 hook 在保存 run 终态前收束尚未结束的阶段和 workflow。持久写入失败会阻止阶段成功，live 回调失败会让 run 终态失败。

`GET /events` 继续使用现有结构，只验证并投影 `analysis.stage` metadata。查询使用认证用户或受信任内部 owner 范围；`DbRunEventStore` 的 user_id 从当前 run 用户上下文绑定。SQLite 集成测试经 emitter 实际写入数据库，并验证 owner 可回放、其他 owner 得到空结果。runtime contract 常量由 App 模块闭合；root JSON 只由定点测试读取，不成为安装或镜像启动依赖。

`verified_report.py` 的固定表头文案改为“数值”，未改其 DTO 或算法。

## 验证范围

V2：本切片跨越阶段序列化、既有事件持久化、认证 owner 投影和 run 终态生命周期。定点测试验证合同一致性与拒绝额外字段、先持久后 live、两类游标分离、阶段顺序、真实失败/取消终态、token/cache 白名单、持久失败关闭、SQLite owner 回放和跨用户拒绝，并复用受影响 tools、reports、Gateway、worker 测试。

- 六个受影响 pytest 模块：`test_analytics_agent_stages.py`、`test_run_events_endpoint.py`、`test_analytics_agent_tools.py`、`test_analytics_agent_reports.py`、`test_gateway_services.py`、`test_run_worker_delivery.py`，`345 passed`。worker 测试额外确认取消时向 finish hook 传入 `interrupted`，以及阶段终态持久化失败会把原 success run 改为稳定错误 `analysis_stage_unavailable`。
- `test_run_worker_delivery.py` 独立模块，`23 passed`。
- `test_analytics_agent_reports.py` 独立模块，`61 passed`。
- 并发报告精确节点与 SQLite emitter→store→owner GET 精确节点，`2 passed`。
- Ruff check 与 Ruff format check 均覆盖 13 个受影响 Python 源码/测试文件，通过；`git diff --check` 通过。

并发报告测试的 `_Repo` fake 原先每次都回 `PUBLISHED`，无法表达生产 repository 按 identity、title 与 evidence IDs 识别的幂等重试。本切片仅为该用例启用 fake 的幂等语义：首次调用发布，重复调用回 `EXISTING`，不调整生产代码迎合测试。

## 未覆盖的集成边界

主会话确认本轮 Docker Engine named pipe 不存在，因此没有可用实时 PostgreSQL 入口。必需的 PostgreSQL 持久写入/回放与容器检查留给统一集成验收；可选 MySQL 未执行。本切片未调用真实模型、部署或容器。实际 SSE 与刷新回放的端到端验收尚未执行，因此本记录不表示 AS09 整体验收完成。

## 终态 live 生命周期修补

独立审查发现 `run_agent` 在关闭 graph stream 后才调用阶段 `finish`。之前 `finish` 复用 Tool 保存的旧 StreamWriter；RunJournal 不会把该分析 custom event 转发到 bridge，因此 durable terminal 已写入时，live 消费者仍可能收不到终态。

回归先在 worker 层重现：假 writer 在 graph stream 结束后拒绝写入。修复前运行 `test_analysis_stage_terminal_payloads_publish_on_bridge_after_graph_stream_closes`，run 实际变为 `error` 而预期为 `success`；日志从 worker finish hook 追到 `AnalysisStageEmitter.finish()` 的旧 writer 调用。修复后 emitter 对终态只做合同校验与持久写入并返回 payload tuple，roles 转交该 tuple；Harness 在 `publish_end` 前通过现有 `bridge.publish(run_id, "custom", payload)` 逐项发送。Tool 阶段仍沿用原有 persist→`aemit_custom_event`。

另一直接节点让终态 `put` 失败，确认 worker 标记稳定 `analysis_stage_unavailable`，且 bridge 没有收到终态 custom payload。精确 stage/worker 回归节点共 `6 passed`；此前六模块组 `345 passed` 的证据予以保留，此次没有重跑该组。5 个受影响 Python 文件的 Ruff check 与 Ruff format check 通过，`git diff --check` 通过。
