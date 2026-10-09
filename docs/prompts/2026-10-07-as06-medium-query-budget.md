# AS-06 MEDIUM 风险预算收紧

执行者：用户指定 `gpt-6-luna` / max。新上下文实施，主会话已读 config.py、delivery.py::_plan_limits 和现有LOW行数clamp测试：当前所有授权查询统一用 AnalyticsConfig.execution_limits，MEDIUM没有降档。这是完整发布契约的确认缺口，不需要重新查全部AS历史。

## 方案与文件所有权

本切片只改 `backend/app/analytics/application/delivery.py`、必要 `backend/app/analytics/config.py`（优先不增加配置键）、直接 `backend/tests/test_analytics_delivery.py` 与需要的config测试、`backend/docs/CONFIGURATION.md`/`backend/app/analytics/AGENTS.md`当前限额说明、acceptance新报告 `docs/acceptance/2026-10-07-as06-medium-budget.md`。PROGRESS由后续主会话状态收口处理，勿并行修改。没有frontend/SDK/新角色/持久化schema改动，不部署/模型/真实数据库。本轮已有全量工作树diff不得覆盖。

主会话冻结预算策略：

- LOW沿用现有全局配置，继续`min(configured.max_result_rows, authorized.prepared.row_limit)`。
- MEDIUM按服务器全局三个预算分别减半（向下取整），statement_timeout领域合法下界100ms，row/byte下界1；其余connection/cancellation/EXPLAIN/cost/column/TTL不变化。不引入客户端覆盖、不读取未经验证的request risk，只用**semantic authorization返回的AuthorizedQuerySpec.risk**。
- 先将全局MEDIUM行预算减半，再与SQL授权row_limit取min；SQL LIMIT1不会因为与LOW最终effective cap相同而被误拒绝。比较严格收紧针对全局预算，而不是SQL已更紧的限制。
- 如果服务器全局配置某项本已到不可收紧的合法下界（timeout100ms、rows1、bytes1），MEDIUM不能静默以LOW预算执行。明确以既有`cost_limit_exceeded`拒绝、无plan签发、无EXPLAIN/execute；写稳定拒绝审计，audit失败保持audit_unavailable。不改变LOW接受这些下界的兼容性。
- HIGH/无授权原有fail-closed逻辑不变。风险预算必须进入现有一次性plan持久payload，执行路径不能重新放宽。

采用最简单现有模式：`dataclasses.replace`保持领域不变量；不用新framework/helperwrapper。如直接_plan_limits ValueError以表达预算不可收紧，execute需在调用create_plan前单独把这个已知拒绝转cost_limit_exceeded并记审计，不能混入现有database_unavailable兜底而丢审计。审计phase选当前领域定义允许且贴合拒绝发生阶段的一项，稳定reason不要携带SQL/配置secret。

## 定点验证（V2）

先新增行为回归并实际RED：MEDIUM与LOW同服务端配置的timeout/row/byte全局预算比较，以及SQL更小LIMIT、下界拒绝/no-plan/audit、LOW不变。使用现有 `_use_case`/`_CreatePlan`/`_Authorizer`fixture，不模拟真实DB和模型。测试授权风险MEDIUM而policy仍LOW的情况，以证明最终权限结论而不是最初syntaxrisk驱动降档；不要伪造非法AuthorizedQuerySpec。

实现后一次运行 `backend/.venv/Scripts/python.exe -m pytest tests/test_analytics_delivery.py tests/test_analytics_config.py -q`（backend cwd），受影响ruff check/format --check（有pytestcollector依赖错误先定点查，不升级deps）。若某config测试未变且证据先前有效也可按直接影响缩范围，不跑全backend。

已有LOW“只clamp行其余固定”测试仍有效，应明确限定LOW，不删保护来让MEDIUM通过。风险预算进入实际plan的契约若仅deliverymock无法证明，定点补/运行现有 execution_plan_store/execution相关test的直接适用case，不机械全套。

报告精确策略、真实RED/GREEN命令/退出码/数量、文件diff、下界/拒绝审计与计划语义；AS06真实双DB超时/截断/events尚未整体验收，不标complete。写相关用户配置说明，不加README仪式性重复。当前未产生真实modelrun/新DB，不触29384/29385容器。每约60秒实际进度，够证据立即实现，不长读架构；不要commit/push。完成后冻结，主会话独立审查自动派下一切片。
