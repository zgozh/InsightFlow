# 正例 run 失败定点诊断（2026-10-09）

**精确根因未知。** 已确认的失败边界是 Data stage 的稳定码 numeric_validation_failed（durable events seq 23、33），最终 workflow 为 failed/unavailable。该码证明数字声明验证路径失败，但不能区分候选闭合结构、单元格引用/数字核验或其它共用该码的拒绝分支。候选 claims/labels 没有保存在 run messages；未再次调用模型。

后续的 authorization/blocked/policy_denied 不是首个失败，也不是终态根因证据。B 的 run 时间窗内有三条 audit：authorization/completed、plan/completed/plan_created、execute/completed/executed。执行 audit 记录 3 行、未截断，schema/policy 版本与 fixture 匹配。per-run messages 中首个 query_business_data ToolMessage 同样是 executed、3 行、未截断且带 evidence。

只读诊断以合成用户 B 读取既有 run：messages API 返回 17 条，递归解析到 8 条 ToolMessage；后续 ToolMessage 的安全提取未得到稳定 decision code，因此不能据此判断具体拒绝字段。run events API 返回一条 run.error；安全摘要未提取到 exception type。响应内容只在内存中过滤，没有输出或保存错误正文、SQL、模型/provider 文本或结果行。

安全摘要位于：

- .reviews/final-postgres-runtime-20261008/runtime-probes/runtime-probe-failure-diagnosis.json：B-scoped audit 时间窗摘要。
- .reviews/final-postgres-runtime-20261008/runtime-probes/runtime-probe-message-envelope-diagnosis.json：per-run messages、ToolMessage 形状、候选是否持久化及 run.error 安全字段。

源码定位：

- backend/app/analytics/agent/roles.py 的 _parse_data_result（约 498 行）把顶层键、数组及字段类型不满足合同映射为 invalid_response。_claim_from_json（约 471 行）和 _reference_from_json 对结构类型正确、但领域值不合法的对象会映射为 numeric_validation_failed；claim/label ID 集合不一致及 verify_numeric_claims 的拒绝也映射为同一个 numeric_validation_failed。因此 durable code 不能辨别具体子分支。
- Data 角色通过 _invoke_role（约 691 行）直接调用并解析响应，调用配置不挂 run callbacks；分析候选不会进入普通 thread messages。backend/app/analytics/agent/reports.py 的 Data 捕获分支将稳定码写入阶段事件，并向工具调用方返回 analysis_role_<reason>。backend/packages/harness/deerflow/runtime/serialization.py 对报告工具结果只保留白名单码，未知码降为 analysis_report_result_unavailable。
- backend/packages/harness/deerflow/runtime/runs/worker.py 的异常终结路径将 exception class 放入 run.error event 的 name 字段（约 1552 行）；此次 B 可见的安全事件 envelope 未提供可用 exception type，最末 worker exception class 仍未知。
- _DATA_PROMPT（roles.py 约 73–95 行）包含闭合 JSON 形状、引用字段约束及占位示例，没有基于本次 evidence 的完整合法 claim 示例。这是源码观察，不足以断定 live 候选格式错误。

最小下一步建议：在现有 _parse_data_result / verify_numeric_claims 上做一次无模型函数级重放，使用本次成功 fixture evidence 形状构造确定合法候选，再覆盖闭合结构、引用和值校验的最小拒绝样例。它能验证现有解析合同边界，但不能替代缺失的 live 候选，也不能确定本次 numeric 子分支。优先复用现有函数和测试辅助，不新增运行链路或可观测框架；在得到 live 候选前不建议改生产提示或放宽验证。

本次运行 diagnose_existing_run.cjs 的语法检查，以及有界 B-scoped 只读提取：audit 页一次、message/error envelope 一次。没有运行模型、没有修改生产代码或重启/重建容器。本记录不表示正例验收或整体发布验收通过。
