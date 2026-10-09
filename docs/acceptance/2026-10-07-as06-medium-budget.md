# AS-06 MEDIUM 查询预算收紧

本切片修复受控查询交付中的风险预算缺口。限额只在语义授权通过后按 `AuthorizedQuerySpec.risk` 派生；不读取客户端风险值，也不增加配置项。

LOW 沿用服务器全局预算，并将全局 `max_result_rows` 与授权 SQL 的 `row_limit` 取较小值。MEDIUM 将全局 `statement_timeout_ms`、`max_result_rows` 和 `max_result_bytes` 各自减半并向下取整，分别保持 100ms、1、1 的领域下界；行数收紧完成后再与 SQL `row_limit` 取较小值，因此小 `LIMIT` 不会因 MEDIUM 预算而被误拒绝。若任何全局预算已到下界、无法严格收紧，则在 plan 创建前写 PLAN 阶段拒绝审计并返回 `cost_limit_exceeded`；审计失败返回 `audit_unavailable`，且不签发 plan。其余限额保持启动配置值。

计划创建用例接收派生后的完整 `ExecutionLimits`，并将其写入 `StoredExecutionPlan`；执行从已领取的计划继续使用该值。现有 SQLite plan-store round-trip 定点用例通过，存储 schema 与 codec 未改动。

验证均从 `backend/` 目录运行：

- RED：`.\.venv\Scripts\python.exe -m pytest tests/test_analytics_delivery.py -q -k 'medium_risk_halves or medium_budget_does_not_reject or medium_budget_at_a_global_floor'`，退出码 1，`4 failed, 1 passed, 20 deselected`。新失败证明 MEDIUM 未减半，且三个预算下界仍能签发 plan；小 LIMIT 场景通过。
- GREEN：`.\.venv\Scripts\python.exe -m pytest tests/test_analytics_delivery.py tests/test_analytics_config.py -q`，退出码 0，54 passed。
- 新增审计 start/finish 失败断言：`.\.venv\Scripts\python.exe -m pytest tests/test_analytics_delivery.py -q -k 'medium_budget_floor_refusal_returns_audit_unavailable'`，退出码 0，2 passed，25 deselected。
- plan payload 保持：`.\.venv\Scripts\python.exe -m pytest tests/test_analytics_sql_plan_store.py::test_a_plan_round_trips_and_is_consumed_once -q`，退出码 0，1 passed。
- `.\.venv\Scripts\python.exe -m ruff check app/analytics/application/delivery.py tests/test_analytics_delivery.py`，退出码 0。
- `.\.venv\Scripts\python.exe -m ruff format --check app/analytics/application/delivery.py tests/test_analytics_delivery.py`，退出码 0；两个文件已格式化。

本报告只确认 MEDIUM 预算派生与拒绝门禁。AS-06 的 PostgreSQL/MySQL 真实超时、截断与事件整体验收仍未完成，因此不宣告 AS-06 完整通过。
