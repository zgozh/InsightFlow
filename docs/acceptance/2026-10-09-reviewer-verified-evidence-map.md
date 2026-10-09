# Reviewer 已验证证据映射验收

报告生成路径把 Data 角色经固定算式校验得到的 `VerifiedNumericClaim` DTO 传给 Reviewer，并以闭合字段投影声明 ID、操作、计算值、operand 引用、unit/period 与各自引用角色、舍入状态及快照截断状态。Reviewer 不接收模型自由声明或任意字典作为 verified map。

每个引用必须指向当前 run 允许的成功快照、存在的行和唯一列；claim 数量、单 claim 引用数及序列化字节数有界。映射参与 Reviewer 决策缓存指纹，不能借用同一 Markdown/evidence 下另一份映射的旧结论。没有映射的旧式直接 Reviewer 调用仍保留旧 payload；受控发布路径始终显式传入已验证 DTO。

Reviewer prompt 区分 `columns/rows` 源数据、确定性验证映射和 evidence/指标目录元数据。ID、hash、版本、行数、行索引和指标目录定义不是经营数值；映射也不证明业务口径或完整性。真实矛盾、缺失支持或模型拒绝仍阻止发布，调用上限保持两次。

离线回归覆盖报告路径传递 DTO、带角色的序列化、非法 shape/越界引用 fail closed、映射参与缓存键、输入预算和模型拒绝不发布。未运行模型或部署；定点检查命令：

```text
uv run pytest tests/test_analytics_agent_reviewer.py tests/test_analytics_agent_reports.py -q
uv run ruff check app/analytics/agent/reviewer.py app/analytics/agent/reports.py tests/test_analytics_agent_reviewer.py tests/test_analytics_agent_reports.py
uv run ruff format --check app/analytics/agent/reviewer.py app/analytics/agent/reports.py tests/test_analytics_agent_reviewer.py tests/test_analytics_agent_reports.py
```
