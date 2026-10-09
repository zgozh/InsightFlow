# 耐久查询证据基础验收

本切片完成 ADR0005 第 1 步的 domain/application/persistence 基础。既有 `AnalyticsQueryEvidence`、
`AnalyticsQueryToolResult` 与摘要算法迁至纯 domain 模块；`agent.evidence` 保留原公共导入，
`AnalysisRunEvidenceCollector` 的位置与行为保持不变。

`StoredAnalysisEvidence` 绑定 principal/thread/run、成功结果、UTC 时间和唯一服务端路径；evidence ID
由结果派生。记录校验固定成功状态、decision、摘要、字节数与结果一致，拒绝未知标量、非有限数字、超界
列/行/快照和模型自选路径。版本 1 codec 采用精确 JSON 键集合，先限制 UTF-8 payload 大小再解析，并拒绝
重复键、bool 冒充整数、非规范 Decimal、未知版本及损坏 payload。

新增 `analytics_query_evidence` 表与 0003 纯追加迁移。复合主键为 principal/thread/run/evidence，表无
Harness 外键；快照字节有非负约束。SQL 仓储按精确 run 范围事务串行检查每 run 20 条、快照合计 16 MiB，
相同结果幂等，冲突不覆盖。SQLite 使用 `BEGIN IMMEDIATE`，PostgreSQL 使用独立 transaction advisory
lock。读取必须完整命中、校验后按请求顺序返回；缺项、损坏或越权范围整体失败。composition 复用共享
应用库 session factory 暴露可选 repository 属性，兼容尚未接入 evidence bridge 的普通构造。

验证结果：

- 首轮定向组：83 passed、1 failed；唯一失败是 analytics domain 边界测试的标准库 allowlist 未包含新增
  domain 模块使用的 `hashlib` 与 `json`。将这两个标准库加入 allowlist 后，边界与 collector 定向复验为
  **44 passed**。
- 首轮仓储、SQLite reopen、容量/竞争、codec 与迁移组均通过；最后对仓储输入边界作小幅修正后，重新运行
  `tests/test_analytics_durable_evidence.py`：**11 passed**。
- 受影响 Analytics Python 文件的 `ruff check` 通过，`ruff format --check` 通过；`git diff --check` 通过。
- 本切片仅验证 SQLite；PostgreSQL 锁与竞争没有实测。

精确命令（均从 `backend/` 运行）：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analytics_durable_evidence.py tests/test_analytics_persistence_migrations.py tests/test_analytics_agent_evidence.py tests/test_analytics_composition.py tests/test_analytics_boundaries.py -q
.venv\Scripts\python.exe -m pytest tests/test_analytics_boundaries.py tests/test_analytics_agent_evidence.py -q
.venv\Scripts\python.exe -m pytest tests/test_analytics_durable_evidence.py -q
.venv\Scripts\ruff.exe check app/analytics tests/test_analytics_durable_evidence.py tests/test_analytics_composition.py tests/test_analytics_persistence_migrations.py tests/test_analytics_boundaries.py
.venv\Scripts\ruff.exe format --check app/analytics tests/test_analytics_durable_evidence.py tests/test_analytics_composition.py tests/test_analytics_persistence_migrations.py tests/test_analytics_boundaries.py
```

后续 Gateway/tool bridge 仍需把成功查询写入仓储并从固定 artifact 能力发布结果；analysis admission 必须在
repository 缺失时 fail closed。本验收不表示 query 已写 artifact，也不表示真实 run 重启恢复已验收；角色链、
Reviewer 与其余 AS07/10/12 门禁仍待后续切片。

## 2026-10-08 独立审查补正

独立审查发现 `AnalyticsQueryToolResult` 的证据约束只在非空 `rows` 时生效，导致失败结果携带 evidence、
以及没有 evidence 的零行成功结果都能先通过 DTO 构造。DTO 现在拒绝失败码携带 evidence，也要求零行成功结果
携带 evidence；零行且有 evidence 时复用 `validate_successful_query_result`，因此行数、摘要或字节数与空结果不符会在
DTO 入口拒绝。普通失败码的空 DTO 仍可构造。非空结果的完整摘要校验仍由 collector、codec 和持久化记录边界执行。

首轮审查定点运行得到 58 passed、1 failed；唯一失败是旧测试仍期待“失败码 + evidence”可先构造、再由 validator 拒绝，
与修复后的 DTO 契约不符。更新该断言并增加合法零行、缺 evidence 零行及错配零行的入口覆盖后，当前定点组为 **59 passed**。
`ruff check`、`ruff format --check` 与 `git diff --check` 均通过。

本次精确检查（从 `backend/` 运行）：

```powershell
uv run pytest tests/test_analytics_agent_evidence.py tests/test_analytics_durable_evidence.py tests/test_analytics_boundaries.py -q
uv run ruff check app/analytics/domain/evidence.py tests/test_analytics_agent_evidence.py tests/test_analytics_durable_evidence.py tests/test_analytics_boundaries.py
uv run ruff format --check app/analytics/domain/evidence.py tests/test_analytics_agent_evidence.py tests/test_analytics_durable_evidence.py tests/test_analytics_boundaries.py
git diff --check
```

此次只修正 DTO evidence 边界并更新本验收记录；未验证 Gateway/tool bridge 接线、artifact 发布或真实 run 恢复。
