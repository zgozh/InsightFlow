# 已有正例失败定点诊断

实施者 gpt-6-luna/max。只读诊断，不修生产、不调用任何模型、不删除既有 claim。读取根/backend 指南与 `docs/acceptance/2026-10-09-postgres-positive-analysis-live.md`。

所有权仅 `.reviews/final-postgres-runtime-20261008/runtime-probes/` 自己的只读诊断脚本/安全摘要，以及 `docs/acceptance/2026-10-09-analysis-positive-failure-diagnosis.md`。不重建重启容器、不改真实用户权限、不碰旧29384。

私有 context `positive-analysis-private-context.json` 已保存准确 opaque IDs；DPAPI runner/只读恢复 helper 可复用。目标29388，既有单次 run：34条阶段，首次 SQL/authorization/execution 成功并产生3行1份证据；随后 policy_denied、SQL attempt_limit、两次 numeric_validation_failed，最后 workflow/failed/unavailable。**不能只把第二次查询拒绝当作最终根因**：首份证据已经成功，须找 Data 校验的真实失败原因与最终 worker error 稳定类型。

最短路径：

1. 使用同一合成 B 会话只读查看既有 run/messages/state/audit（实际API契约优先），内存核对失败工具的稳定 decision code、Data 候选闭合形状与 numeric validator 拒绝分支，以及最末 worker exception 的安全类型。不要输出完整 messages、SQL、模型/provider正文、结果行、凭据或DSN。允许内存处理当前合成数据；摘要只记录稳定码、字段存在/类型/数量、策略中允许的字段是否匹配、校验通过布尔。
2. 对照 `backend/app/analytics/agent` roles/tools 与 numeric 校验实际实现，区分生产接线/提示协议缺陷、模型未遵循闭合结构、fixture策略不匹配。必要时本地无模型函数重放该结构，使用最小现有测试辅助；禁止泛扫整仓/整套测试/变更策略来迎合越权查询。
3. 交回一个明确的主根因、源码定位、最小修复建议与必要回归检查，准确说明尚未知的部分。若API不保留候选结构，应直说，不发新模型补证。
4. 实际诊断事实写短记录即冻结，主会话独立审查再派修复。执行时间集中在读取已有运行，禁止扩张归档/截图/其它场景。

本次为已确认失败的 V1/V2 定点诊断；真实业务正例 V3 尚未通过。用户最终交付仍包括安全/取消、调度、PG重启checkpoint恢复、文档中文默认仅中英文与清理过时文档，全部验收后commit/push。当前不要修改README或实施该清理。
