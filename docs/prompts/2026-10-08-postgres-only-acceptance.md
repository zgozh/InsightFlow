# PostgreSQL 必验范围调整

用户已明确选择“PostgreSQL 必验，保留 MySQL 可选适配”，其余完整发布验收继续。

实施 gpt-6-luna/max，仅修改当前验收范围文档与本次创建的MySQL fixture状态，不动生产源码/已通过历史证据。

所有权：docs/superpowers/plans/2026-10-07-full-release-acceptance.md、docs/PROGRESS.md、docs/INTERRUPTION.md中当前范围描述；docs/acceptance/2026-10-08-postgres-only-acceptance.md；`.reviews/controlled-query-live-20261008/`中仅新增安全状态备注/可选重启步骤，不改旧passed矩阵。

将AS02 MySQL标为可选支持，已有adapter/usecase通过证据保留；不再要求追加MySQL自然语言模型/HTTP/事件验收。AS03 PG与其他Agent/报告/事件/调度/应用PG恢复门禁不削弱。不得宣称整个AS02全部通过或整个发布已完成。不得删除MySQL适配，不顺带改默认compose/SQLite支持。

核对本任务此前创建的专用MySQL项目标签、容器ID与volume确为controlled-query-live fixture后，只stop该新MySQL容器释放资源，保留专有volume、network、DPAPI凭据和历史证据；禁止stop/remove任何原有29384/29385/29386服务。主机拒绝就报告，不能绕过。记录精确目标/状态、安全复用命令，不打印Env/密钥。

V0文档readback/diff加目标容器只读status即可，不再跑oracle/adapter/tests。不重写旧验证结果，也不让未冻结角色接线/阶段事件被写成完成。
