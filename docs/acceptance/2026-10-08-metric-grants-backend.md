# 指标显式授权后端切片验收

## 行为契约

- 指标管理读写按 `owner_id` 精确隔离；跨 owner 与不存在的指标统一返回 404。
- 普通目录只暴露 `active` 指标，且 principal 必须是指标 owner 或拥有该确切指标 key 的显式 grant。
- `draft` 可以预授权，但只在指标切换到 `active` 后可读；`retired` 永不进入目录。撤销后下一次目录读取立即不可见。
- 跨 owner 同 key 可能存在于管理库。若一个 principal 能读到多个同 key 的 active 指标，普通 list 隐去该 key，get 返回 `None`，不会按顺序任取。
- grant 只影响指标目录可见性，不授予 datasource、schema、policy、SQL 或报告权限。
- grant 表只保存 metric owner、metric key、principal ID 和 UTC 创建时间，并通过复合外键引用 Analytics `analytics_metrics(owner_id, key)`。
- 管理端 grant 路由只接受路径中的目标 principal；grant 与 revoke 幂等，响应不包含账号资料。

## 验收范围

定点验证覆盖 repository、管理用例、HTTP 身份/资源边界、迁移空库升级与从 0003 的非空升级/降级，以及 Analytics 模块边界。全量 backend、前端、Gateway 部署和真实业务账号不属于本切片验收。

## 恢复验证

此前 5 个定点文件的 126 项中已有 123 项通过；本次保留该证据，只执行余下 3 个失败用例。三项用例在同一 pytest 调用中实际运行，共 `3 passed`，不是将多个命令的计数相加。唯一 warning 是 Starlette 对现有 `httpx` TestClient 用法的弃用提示。

从 `backend/` 执行的检查：

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; uv run --locked pytest tests/test_analytics_api.py::test_metric_grants_require_admin_and_are_visible_only_after_explicit_grant tests/test_analytics_persistence_migrations.py::test_bootstrap_creates_exactly_the_analytics_tables_from_an_empty_database tests/test_analytics_persistence_migrations.py::test_phase_4_report_table_is_a_pure_forward_addition -q
# 3 passed, 1 warning in 8.23s
```

补上普通账号获授权后可读取指标目录的正向断言后，另行只运行该 API 用例。此结果是针对新增断言的补充验证，不与此前三项相加：

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; uv run --locked pytest tests/test_analytics_api.py::test_metric_grants_require_admin_and_are_visible_only_after_explicit_grant -q
# 1 passed, 1 warning in 5.90s
```

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; uv run --locked ruff format app/analytics/application/management.py app/analytics/infrastructure/persistence/catalogs.py tests/test_analytics_persistence_migrations.py
# 3 files left unchanged

$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; uv run --locked ruff check app/analytics/application/management.py app/analytics/infrastructure/persistence/catalogs.py tests/test_analytics_api.py tests/test_analytics_management.py tests/test_analytics_persistence_repositories.py tests/test_analytics_persistence_migrations.py
# All checks passed!

$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; uv run --locked ruff format --check app/analytics/application/management.py app/analytics/infrastructure/persistence/catalogs.py tests/test_analytics_api.py tests/test_analytics_management.py tests/test_analytics_persistence_repositories.py tests/test_analytics_persistence_migrations.py
# 6 files already formatted

git diff --check -- backend/app/analytics/application/management.py backend/app/analytics/infrastructure/persistence/catalogs.py backend/tests/test_analytics_api.py backend/tests/test_analytics_management.py backend/tests/test_analytics_persistence_repositories.py backend/tests/test_analytics_persistence_migrations.py
# exit 0, no output
```

grant 写入继续使用 SQLite 和 PostgreSQL 的 `ON CONFLICT DO NOTHING` 保证幂等；未知 persistence dialect 会以稳定原因 `metric_grant_unsupported_dialect` 拒绝。尚未部署，前端尚未接入该 API，完整 15 个场景仍未验收。
