# Data 运算计划由服务器计算验收

Data Analyst 的内部闭合 JSON 现在只提供 claim ID、固定 operation、exact evidence cell operands、小数位与单位/期间引用，不接受 `value` 或任何自报计算结果。额外 `value` 字段按 `invalid_response` 拒绝。

`NumericClaimPlan` 不包含数值结果。`calculate_numeric_claim_plans()` 使用现有 exact snapshot 验证、引用解析、固定算式、Decimal 精度与 `ROUND_HALF_UP`，生成原有 `VerifiedNumericClaim` DTO；报告 renderer、Reviewer evidence map 与发布路径保持原样。`verify_numeric_claims()` 的现有公开参数和严格断言值相等检查保持不变。

范围仅是 Gateway 内部 Data Analyst 输出协议。用户 API、冻结 evidence、SQL 授权政策、报告与 Reviewer 契约不变；没有触发模型请求或部署。

验证：

- `test_analytics_numeric_claims.py`：严格断言兼容、计划计算、3 月 cell/合计 `3901.25`、舍入、引用范围、标签来源、重复 ID、除零及有界数字输入。
- `test_analytics_agent_roles.py`：无值结构、拒绝额外 `value`、固定反馈与现有两次调用上限、拒绝错误引用、只把服务器计算结果送入 Writer。
- `test_analytics_agent_reports.py` 和 `test_analytics_agent_reviewer.py`：确认原有 verified DTO 透传、reviewer map 和拒绝不发布行为未受内部 plan schema 变化影响。
