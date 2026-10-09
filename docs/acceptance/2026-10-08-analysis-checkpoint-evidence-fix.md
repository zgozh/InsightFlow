# 显式 checkpoint 续跑证据恢复验收

## 实现结果

- Harness worker 每次运行都以服务端 `record.run_id` 覆盖 checkpoint metadata 中的 `deerflow_analysis_run_id`；客户端同名 metadata 不能指定来源。
- Gateway 仅为显式选中的 checkpoint 读取 producer metadata，并在 analysis admission 中通过 owner-scoped run lookup，再核对 owner、thread 和终结状态。允许 `success`、`error`、`timeout`、`interrupted`；拒绝 `pending`、`running`、不存在或身份不匹配的 producer。无 selector 时不猜测来源。
- analysis collector 只解析当前 run 与一个已验证 producer。每项按其来源的 exact scope 读取并复核固定 artifact，保持请求顺序；重复来源、错误身份、缺记录、损坏 artifact 或超过 20 项/16 MiB 总快照预算都会使整批失败。旧 checkpoint 可继续续跑，但缺 producer metadata 时不能恢复旧 evidence。
- 审查记录中的 success-only 来源建议已修正：`error` 与 `interrupted` run 也可能在结束前留下成功 query，因此只按终结状态筛选；每条恢复的 query 仍须通过 success DTO 与 artifact 完整性核验。

## 定点检查

以下命令均从 `backend/` 执行，使用 `uv run --no-config --default-index https://pypi.org/simple --locked --no-sync`，且未改 `uv.lock`。

- Gateway checkpoint helper、durable evidence bridge/repository、worker metadata stamping 定点节点：`27 passed, 1 skipped`。随后 Gateway helper 节点在加入 `error` 终结来源覆盖、并限制普通非 analysis run 不查询 producer 后再次运行：`6 passed`。
- Bridge 模块在补入错 owner 与跨来源总预算回归后再次运行：`8 passed, 1 skipped`。
- Ruff 对 9 个受影响 Python 文件的 `check` 通过；`format --check` 报告 `9 files already formatted`。
- `git diff --check` 通过；只输出已有工作树文件的 CRLF/LF 提示。`uv.lock` 无工作区改动。

未运行 PostgreSQL live 验收、模型调用、构建或容器。SQLite 定点测试没有证明真实 PostgreSQL 路径；已有 PostgreSQL 发布门禁仍需在其适用阶段执行。
