# 未完成运行恢复验收（2026-10-09）

状态：通过。

在现有 Gateway 容器和预装 Python 环境中，使用独立 PostgreSQL fixture 运行了真实 Gateway lifespan 与 `FakeAgent`。worker 1 的运行记录先确认为 `running`；FakeAgent 阻塞在 checkpoint 前，没有调用模型。随后只终止了该 helper 进程（容器 PID 4623，退出码 137），等待 7 秒使 5 秒 lease 过期，再由全新的 helper 进程启动正常 Gateway lifespan 并读取恢复结果。

生产启动恢复将该运行标记为 `error`，`stop_reason=orphan_recovered`，对应线程为 `error`。合成线程内只有 1 条运行记录；owner 与线程匹配。事件共 1 条，为唯一的 `run.delivery` receipt，内容精确表示零交付。receipt 与事件序列的 SHA-256、run/thread 的脱敏标识哈希及计数见 [安全 proof JSON](../../.reviews/final-postgres-runtime-20261008/unfinished-recovery/unfinished-run-proof.json)。

验证完成后，helper 按精确 DB/role 名称核对所有权、无活动连接、无该 role 所有的其他数据库，再删除本次隔离 DB 与 role；随后只读确认两者均不存在。没有改动 Gateway 服务、配置或模型，也没有扫描或修改应用数据库。

执行器和恢复 helper 保存在 `.reviews/final-postgres-runtime-20261008/unfinished-recovery/`。首次恢复后的只读检查遇到 `BlockingPortal.call` 不接受关键字参数；将检查调用改为 lambda 后，新 helper 进程成功读取已恢复状态，没有再创建运行记录。
