# Phase 2C2 Fix 01 实施提示词：按查询 LIMIT 收紧结果上限

你是 InsightFlow Phase 2C2 修复工程师。只修复 `max_result_rows` 与查询自身 `row_limit` 的交互，不开始 Phase 3，不做其他重构。

## 1. 起点

- `HEAD` 必须是 `568a3d6d202a76502af291f93c28fa7b360ea41f`。
- parent 必须是 Phase 2C2 架构提交 `d42c69ff068e357488f216ff5010c325575de89b`。
- 工作树开始时只应有本提示词这个未跟踪文件。
- 固定 tag `upstream-v2.1.0-rc0` 的 commit/tree 必须保持不变。

## 2. 裁决

当前行为把配置的 `max_result_rows=1000` 原样交给 `CreateQueryExecutionPlan`，导致合法查询
`SELECT ... LIMIT 10` 因 `1000 > prepared.row_limit(10)` 返回 `authorization_stale`。

这不是合理的运维契约。`max_result_rows` 是服务器传输上限，不是每条查询必须达到的下限。

最终规则：

```python
effective_max_result_rows = min(
    configured_limits.max_result_rows,
    authorized.prepared.row_limit,
)
```

在 `PlanAnalyticsQuery` 获得服务端生成的 `AuthorizedQuerySpec` 后，使用不可变复制生成本次计划的
`ExecutionLimits`，只把 `max_result_rows` 向下收紧为上述值；其他限额保持配置值不变。

安全含义：

- 客户端仍不能提交或覆盖任何 limit；
- 结果上限只可能变小，不可能扩大；
- `CreateQueryExecutionPlan` 中 `limits.max_result_rows <= prepared.row_limit` 的校验必须保留，继续作为纵深防御；
- plan payload 保存收紧后的 limits，execute 不得重新放宽；
- 配置层的 `max_result_rows <= query_max_rows` 校验继续保留。

## 3. 必须测试

至少覆盖：

1. 配置上限 1000、查询 `LIMIT 10`：传给 plan use case 的 `max_result_rows == 10`，不再得到 `authorization_stale`；
2. 查询 row limit 高于配置上限：仍使用配置上限；
3. 查询未显式写 LIMIT、由 Phase 2A 应用默认/最大行数：使用两者较小值；
4. 除 `max_result_rows` 外，`ExecutionLimits` 所有字段与配置生成值完全一致；
5. API 层的小 LIMIT 查询可以正常进入 plan use case，客户端仍不能提交 limits；
6. 既有 `CreateQueryExecutionPlan` 对“传输上限大于授权 row_limit”的直接拒绝测试保持通过，不修改或放宽。

## 4. 文档修正

删除“运维必须把 `max_result_rows` 配到用户最小 LIMIT 以下”的说明，改为：

- 配置值是全局服务器上限；
- 每条计划会按 `min(configured cap, prepared row_limit)` 自动向下收紧；
- 这是服务端派生，不是客户端 override。

同步修正 Phase 2C2 架构中“固定 ExecutionLimits”的歧义：除 `max_result_rows` 按授权查询向下收紧外，
其余字段固定来自启动配置。

## 5. 允许修改集合

提交中只允许：

- `backend/app/analytics/application/delivery.py`
- `backend/tests/test_analytics_delivery.py`
- `backend/tests/test_analytics_api.py`
- `backend/app/analytics/AGENTS.md`
- `config.example.yaml`
- `backend/docs/CONFIGURATION.md`
- `docs/architecture/phase-02c2-authenticated-analytics-delivery.md`
- `docs/PROGRESS.md`
- `docs/prompts/phase-02c2-fix-01-query-result-cap.md`（原样提交）

不得修改 Phase 2A/2B/2C1 生产实现、`config.py`、API 契约、依赖、lock、frontend、Docker 或迁移。
若实际需要列表外文件，停止并报告，不自行扩大范围。

## 6. 精简门禁

不要重跑 1049 项套件、Docker 或真实数据库。只运行：

```bash
uv run --locked pytest \
  tests/test_analytics_delivery.py \
  tests/test_analytics_api.py \
  tests/test_query_execution_use_cases.py -q

uv run --locked ruff check \
  app/analytics/application/delivery.py \
  tests/test_analytics_delivery.py \
  tests/test_analytics_api.py

uv run --locked ruff format --check \
  app/analytics/application/delivery.py \
  tests/test_analytics_delivery.py \
  tests/test_analytics_api.py

git diff --check
```

所有 `uv` 命令使用 `--locked`；不得修改 `backend/uv.lock`。

## 7. 提交纪律

- 只创建一个提交：`fix: clamp analytics result cap to query limit`
- parent 必须是 `568a3d6d202a76502af291f93c28fa7b360ea41f`。
- 完成后工作树干净，Phase 3 未启动。
- `docs/PROGRESS.md` 仍保持 Phase 2 为 `In progress`，next gate 写 `Phase 2C2 Fix 01 GPT 复验`。

## 8. 最终回复

用中文简要报告 commit/parent、精确文件集合、RED/GREEN 与门禁计数，并证明：

- 小 LIMIT 被自动收紧后可以创建 plan；
- 其他限额没有变化；
- 客户端仍不能覆盖 limits；
- 2B2 防御性校验未修改；
- lock、固定 tag/tree、工作树未漂移；
- Phase 3 未启动。

不要自行宣告 Phase 2C2 最终验收通过，等待 GPT 复验。
