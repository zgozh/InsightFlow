# 修复展示标签阻断报告

gpt-6-luna/max。主会话独立审查 c5a7 重测记录与 ReportClaimLabel：两次固定诊断均为 label_domain，合法数值声明离线已通过。标签只承担展示，不证明业务语义；不合规自由标签不应让已有可验证数字永远无法发布。

所有权仅 roles.py、test_analytics_agent_roles.py 与 docs/acceptance/2026-10-09-data-display-label-repair.md。当前不部署、不模型、不其它文件。

在既有 _parse_data_result 内最小修复：保留 claims/labels 闭合形状、类型、数量、唯一ID/集合对应检查，保留所有 NumericClaim/引用/verify_numeric_claims 校验。合法标签原样保留；对于合法对应 claim_id 的展示文本不满足 ReportClaimLabel 规则（数字字符、空/空白、过长、控制字符等），丢弃该文本，以对应 NumericClaim.operation 的固定安全展示名构造标签（cell数值、sum合计、difference差值、ratio比率、percentage占比、mean均值、change_percentage变动比例）。所有替代名必须满足原领域的无数字要求，不修改 ReportClaimLabel 或 renderer 规则。

不得通过标签归一化接纳未知/非法/重复claim_id，不吞掉数值/引用/算术验证失败，不使用不可信文本拼出新标签，不把完整标签/候选写日志。使用现有函数和标准字典即可，无新层/兼容框架。如记录归一化日志只写固定消息，原其它4个拒绝分支安全诊断保留；label_domain原拒绝回归改成正确的固定替代行为。

最小回归：真实失败边界的数字/空/过长/控制文本固定替代，合法标签保留；所有operation固定名通过领域校验；未知/重复ID、伪造数值或引用继续拒绝。复用现有快照与parser，运行该测试文件一次+两文件Ruff check/format --check，V1。交实际代码/精确checks后冻结，主会话独立审查再推进一次有具体修复依据的真实API。
