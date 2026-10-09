# AS09 阶段事件 v1 合同记录

本切片只冻结事件合同，未实现生产 emit、持久化写入或前端 consumer；不代表 AS09 完成。

- SSE 保持 `event: custom`，业务名固定为 payload `type: "analysis_stage"`。Payload 使用 [`analysis-stage.v1.json`](../../contracts/analysis-stage.v1.json) 的闭合对象与 `version: 1`。
- `run_id` 是运行身份；`seq` 是 payload 内 per-run 正整数，用于 live 与永久回填按 `(run_id, seq)` 去重。它不替代 SSE `Last-Event-ID` 或 thread-global `run_events.seq`。
- `stage`、`status`、`risk`、`code` 均为 schema 固定枚举。可选计数、时长、token 数均有整数上限；未知值省略。`evidence_ids` 最多 20 个、唯一、每项为 64 位小写 hex。
- `additionalProperties: false` 禁止扩展字段，因此不得发送 SQL、结果行、secret、DSN、plan token、自由文本或 CoT。生产侧须将 domain 错误映射到固定 `code`。
- 后续实现需先持久化再 emit 同一 payload；终态失败/取消须映射真实结果；前端须 strict 解析并按 `(run_id, seq)` 去重，再通过持久 `GET /events` 回填。Stage token usage 只能使用实际 usage，未知时省略，不得从 run 总量拆分。

本切片仅对 JSON 进行可解析性及合同字段约束校验；未运行源码测试或容器，也未触及其他实施者文件。
