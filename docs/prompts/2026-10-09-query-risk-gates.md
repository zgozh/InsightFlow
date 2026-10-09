# 补齐查询安全剩余边界

gpt-6-luna/max。刚完成的直连矩阵已独立审查，复用其登录/CSRF/API helper，不重跑那11类拒绝，不发模型、不改生产/B正常授权。

所有权 `.reviews/final-postgres-runtime-20261008/security-probes/` 与 `docs/acceptance/2026-10-09-query-risk-gates.md`。允许管理员在现有应用创建**独立合成数据源/schema/policy**，复用fixture只读secret_ref；不得改既有主分析source/metric/policy或业务表数据。

先有界读现有risk分类、limits、PG adapter及直接测试，选已实现可触发路径。补：已存在但无B授权source与random source统一拒绝；HIGH/敏感列审批拒绝（不签plan、不执行）；MEDIUM预算裁剪（plan限额与实际有界结果）；真实PG statement_timeout/cancel清理（优先现有adapter真实fixture工具，无模型）。能通过现有API证明的直接API，adapter边界可用已建立真实fixture脚本，不编造不存在的HTTP状态/规则。

配置限额/timeout如需修改，仅独立fixture请求支持的字段；不能改生产全局/B正常配置迎合测试。确有必要受控临时配置时先交精确方案，不自行扩大权限。不要试图让HIGH真正执行，也不能通过移除PII标签放行。

每项记录实际稳定code/预算/计数/超时类型与事务后连接可再用布尔；禁SQL/body/results/password日志。如果确认接口设计使某项无法HTTP触发，依据实际source/tests指出具体机制，复用仍有效的测试证据，不无限扫仓。必要定点验证只运行相关一两项，不全suite。

结束短记录冻结，下一步调度与重启恢复，不再追加相关性弱的安全场景。
