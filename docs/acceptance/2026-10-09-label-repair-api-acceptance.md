# 展示标签修复真实 API 验收

## 结果

单次 `positive-model-run-label-repair.claim` 对应的分析 run 成功，未再次调用模型。只读续验复用了该 run 的私有 context；claim 保留。Gateway 派生镜像为 `sha256:31e27efc80a0fc11d1c76ad54bf37cad4f9afc634bb828591357365318dc476f`，Frontend 仍为 `sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c`。身份守卫确认目标四服务均运行、镜像匹配，Nginx 仍是唯一 loopback 发布端口。

展示标签的真实报告结果确认了探针误判：旧正则命中 6 次“元”，其中指标说明列 3 次、计算说明列 3 次，固定 renderer 列之外为 0。探针现在按 renderer 的六列表格契约校验结构，并要求 8 行的单位列均为“未提供”；仍拒绝明确货币符号、币种代码、“美元”和“人民币”。四个数值 `1200.50`、`1800.00`、`900.75`、`3901.25` 均匹配，查询证据 scope、月度结果与内容摘要校验通过。

报告索引仅有该 run 的 1 条 published 记录。报告和查询证据的 preview/download API 均返回 200，内容相同并带附件 disposition。普通用户 owner 范围内找到 3 条与查询证据匹配的完成审计。浏览器报告卡片及下载入口可见；仅本人审计可见；分析阶段面板刷新后仍有 9 个阶段项。

阶段事件共 32 条，成功链和 workflow 成功终态通过；存在一次成功后的 SQL 阻止尝试，稳定 code 为 `attempt_limit`。只读续验没有 live SSE，`live_and_durable_stages_match` 记录为 `not_rechecked_read_only_resume`，不代表匹配或不匹配。前置 roles 修复的 35 项相关测试及静态检查已通过；本次只读续验未重跑。

## 实际命令与证据

```powershell
& '.reviews/final-postgres-runtime-20261008/runtime-probes/run_analysis_runtime_label_repair.ps1' -ExpectedGatewayImageId 'sha256:31e27efc80a0fc11d1c76ad54bf37cad4f9afc634bb828591357365318dc476f' -ExpectedFrontendImageId 'sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c' -ReadOnlyResume
```

只读续验结果为 `outcome=passed`。安全摘要保存在 `.reviews/final-postgres-runtime-20261008/runtime-probes/runtime-probe-label-repair-resume-evidence.json`；原始 run context 和 claim 均保留。
