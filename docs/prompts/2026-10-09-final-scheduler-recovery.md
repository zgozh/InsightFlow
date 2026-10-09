# 最后集成验收：调度、取消、PostgreSQL恢复

实施 gpt-6-luna/max，根/backend指南适用。已通过的报告链、API安全矩阵、MEDIUM裁剪、HIGH拒绝和真实PG adapter超时证据复用，禁止重跑。不再扩架构/写新通用测试框架。

所有权 `.reviews/final-postgres-runtime-20261008/final-integration/` 与 `docs/acceptance/2026-10-09-final-scheduler-recovery.md`。生产源码只读；若确认真实缺陷先交定位/最小修建议，不擅自扩大。只操作29388四服务与现有PG fixture，不旧29384/其它项目、不删卷、不创建新栈。

使用同一合成B DPAPI与已成功run的 `runtime-probes/positive-analysis-label-repair-private-context.json`。已有主报告数值/evidence hashes保留。

V3剩余场景在同一切片连续执行：

1. AS11：直接scheduled tasks API创建独立合成**分析**任务，优先reuse_thread已持久analysis thread，明确fresh-thread默认是否chat；不能把普通chat产物冒充受控分析。按现有接口触发一次（run-now可证明完整调用链，自动到期需覆盖scheduler实际启用调度），确认非交互、不等待clarification、最终report artifact及owner索引。避免cron反复触发付费调用：唯一任务/occurrence/run标记，完成立刻disable，不能失败盲重发。有完整批准单次模型调用授权，当前只允许本切片调度一次。若enabled配置未开启，可仅对验收栈独立配置启用既有scheduler并保持其余配置，不改源config/secret；说明实际改动并需要受控Gateway restart。不同程序不能覆盖同一认证配置。
2. AS08取消/失败：复用已真实失败的两run终态、次数上限证据与既有直接契约测试；若cancel必验未覆盖，用已建立的本地mock角色/模型运输在现有测试执行器定点验证实际worker cancel，而非为取消再付费调用真实模型。明确这是哪个层，不伪称HTTP实测。优先既有对应passed测试，只补缺证据。
3. AS12：取得成功analysis checkpoint、report/evidence/metadata hash后，受控重启现有Gateway和PG（先PG就绪，再Gateway；其它容器不动），确认owner历史、checkpoint、事件/报告/查询artifact哈希不变，前端已有成功thread仍可查看。未完成run恢复以既有直接真实持久化检查或独立合成记录证明，不伪装success。
4. 显式checkpoint续跑必须验证旧producer证据可被允许复用：先通过实际checkpointer/collector工具做无模型同一producer scope校验与artifact/hash；若合同必须真实新run报告且证据不足，则先向Principal报告具体缺口和已覆盖证明，不自动扩大付费次数。不得放宽owner/thread/run scope或复制旧evidence为新run。普通resume默认不自动授权旧run。

登录/CSRF/read-only helpers从已有runtime/security-probes复用，只写本切片小脚本文件，禁止node -e长命令、PS5 BOM遗漏、FROM裸sha/Compose stderrStop老坑。必要源码读取限scheduled_tasks router/service、run/checkpointer边界与相关直接测试，不重读全部历史。

输出安全状态/code/count/hash与actual gates，禁密码/DSN/SQL/results/messages/provider正文。真实缺陷一处最小修复须先Principal审查，但其它独立检查继续。完成短表每个AS证据/限制立即冻结，随后文档清理与最终commit/push，当前不提交。
