# AS09 固定阶段事件合同

gpt-6-luna/max。仅新增 `contracts/analysis-stage.v1.json`（JSON Schema Draft 2020-12）与 `docs/acceptance/2026-10-08-analysis-stage-contract.md`。其他实施者正在改集成和独立fixture，本任务不读/改其输出、不运行源码测试/容器。

已知已有SSE封装：`event: custom`，data是payload；业务名来自payload.type。永久run_events与SSE缓冲游标不同，因此payload单独带per-run seq供live/持久回填去重。不得改成另一个SSE事件名。

冻结payload对象，additionalProperties=false：

- 必须 type="analysis_stage"、version=1。
- run_id：string，pattern `^[A-Za-z0-9_-]{1,64}$`。
- seq：integer，1..2147483647；不能用thread-global run_event.seq代替。
- stage enum：workflow、catalog、sql、authorization、execution、data、writer、reviewer、publish。
- status enum：running、succeeded、failed、blocked、cancelled。
- 可选 duration_ms 0..86400000；row_count 0..1000000；byte_count 0..16777216；input_tokens/output_tokens 0..10000000，全部integer，未知省略。
- 可选 risk enum LOW/MEDIUM/HIGH/BLOCKED；cached boolean。
- 可选 code enum ok、unavailable、invalid_request、invalid_response、numeric_validation_failed、attempt_limit、input_too_large、policy_denied、cost_limit、query_failed、query_timeout、result_limit_reached、evidence_unavailable、review_rejected、report_conflict、cancelled。生产需将domain现有码映射到这些固定码，不能接受自由错误文本。
- 可选 evidence_ids：uniqueItems=true、最多20项、每项64位小写hex。不得携带SQL/rows/secret/DSN/plan token/自由text/CoT。

记录契约及尚待实现：服务端先持久再emit同payload、终态失败/取消真实映射、前端strict解析+按(run_id,seq)去重、永久GET events回填。tokens必须来自实际usage，未知不从run总数拆算。没有实现consumer或生产emit，不写AS09完成。

校验JSON可解析、$schema/id、字段/required/enums/bounds与冻结提示相符即可；不写多余测试脚本/通用代码生成器。快速冻结返回准确新增文件与检查。
