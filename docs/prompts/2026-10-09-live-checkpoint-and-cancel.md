# 真实持久化checkpoint复用与取消边界

gpt-6-luna/max。独立所有权 `.reviews/final-postgres-runtime-20261008/checkpoint-final/` 与 docs/acceptance/2026-10-09-live-checkpoint-and-cancel.md。另worker只schedulerAPI，不碰这些文件，你不重启/更新Docker服务，不模型、不修改生产。

复用当前已有PG appcheckpointer、原成功analysis context `runtime-probes/positive-analysis-label-repair-private-context.json` 与repo evidence。此前7测试mock不能冒充live。直接在现有Gateway里通过生产service apply_checkpoint或明确checkpoint_tuple producer metadata提取+真实SQL runstoreowner terminal核对，实际EvidenceCollector在指定当前newrun+selectedproducer范围从真实SQLrepository及原artifact读证据；正确owner/thread/producer通过，错误owner/wrongthread/nonterminalproducer拒绝，原artifact hash与domain内容地址不变。可构造独立合成newrun scope仅内存，不创建假success或改旧DB记录，不将old evidence重写为newscope。必要script stdin→docker exec -i appvenvpython，无环境/SQL/候选输出，仅布尔/count/hash。

取消优先实际Runtime已有未完成run合成fixture由真实service/worker取消，模型使用现有local mock或阻塞sandbox动作，无付费模型，无副作用。不能往真实DB手写success；若缺合成harness无法在合理范围liveAPI验证，就执行一条直接worker cancel契约测试并明确层级，不为“live”造新框架。run状态cancelled/interrupted、event/receipt、底层取消传播（与PGtimeout已实测清理合并作分层证据）。

对AS12unfinished恢复，可借已有failedscheduled/取消terminal在当前数据库状态正确持久、重启已经发生的proof组合，但不伪称未完成状态跨重启实测。先给真实PGproducer/collectorproof最短实现并执行，不全源码深挖，不重跑全部tests。短记录exactchecks/仍不足边界立即冻结。
