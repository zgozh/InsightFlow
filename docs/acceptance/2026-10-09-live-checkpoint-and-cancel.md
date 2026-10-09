# PostgreSQL checkpoint 复用与取消核验（2026-10-09）

现有 PostgreSQL Gateway 上的只读 proof 通过，结果保存在 [live-checkpoint-proof.json](../../.reviews/final-postgres-runtime-20261008/checkpoint-final/live-checkpoint-proof.json)。真实 checkpointer 读取 44 条 checkpoint，其中 17 条属于原成功 producer；其 checkpoint metadata 与原 context 匹配，SQL RunRepository 确认 owner/thread 匹配且终态为 `success`。错误 owner 的 run 查询和错误 thread 的 checkpoint 查询均不可见。

真实 `SqlAnalysisEvidenceRepository` 与 `DurableAnalysisRunEvidenceCollector` 在临时内存 scope 中解析出 1 条原 producer evidence。正确 scope 通过，错误 owner、错误 thread 被拒绝；原 artifact 的内容地址有效，domain payload SHA-256 为 `3f1f5eb762bb0cf62739718d0563cf5b6a77e69288b12375e07b5e3a44013c25`，artifact 原始 SHA-256 为 `85394ccc8744c2419f5b1b3b534ff4f185c4937b08d39c255cd4fa4e2880cd05`，两者在读取前后不变。artifact hash aggregate `16b92633c2b7448a4ef7a19624c7c8f23f1c47d4340b1123f6ef0e9d9a02309a` 与既有 runtime probe 一致。合成的新 run scope 仅驻留内存；本核验没有写数据库、修改 artifact 或更改服务。

在 `backend/` 执行的定点测试：

```text
uv run --locked pytest tests/test_gateway_services.py::test_apply_checkpoint_returns_only_terminal_owner_thread_producer tests/test_runtime_lifecycle_e2e.py::test_cancel_interrupt_stops_running_background_run -q
6 passed, 1 warning in 29.85s
```

终态/owner/thread 过滤由第一项的 service 测试替身覆盖；第二项通过隔离的 fake-agent HTTP 测试验证 `action=interrupt` 会取消 worker，并将 run 持久化为 `interrupted`、thread 恢复为 `idle`。测试未调用模型，也不是对生产 Gateway 发起 live cancel。PostgreSQL adapter 的 statement-timeout 与连接/事务清理已有[风险门禁记录](2026-10-09-query-risk-gates.md)，属于另一层证据，不代表 HTTP plan/execute 超时链路通过。

生产运行中的 live HTTP cancel，以及未完成 run 跨 Gateway 重启后的终态恢复，仍未由本次核验覆盖。
