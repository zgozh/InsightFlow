# PostgreSQL 必验、MySQL 可选的范围记录

日期：2026-10-08<br>
范围：AS-01～AS-15 完整发布验收继续；本记录只调整 AS-02/AS-03 的数据库验收边界，不代表相关场景或整体发布已通过。

## 最新裁决

用户明确选择 PostgreSQL 必验，并保留 MySQL 可选适配。AS-03 的 PostgreSQL 真实分析验收仍是必需门禁；AS-02 的 MySQL adapter/usecase 保持可选支持，已经取得的 adapter/usecase 证据继续有效。后续不要求追加 MySQL 自然语言模型、HTTP 或事件验收。

这项调整不删除 MySQL 适配，不改变默认 SQLite 或其 Compose 支持，也不降低 AS-03 PostgreSQL 和其他发布场景的验收要求。不得据此宣称整个 AS-02、AS-03 或完整发布已通过。

## 保留的证据与待验范围

- 历史 MySQL adapter/usecase 覆盖与限制见 [AS-02/AS-03 契约对照](phase-06d-contract-reconciliation.md) 及 [完整发布差距盘点](2026-10-07-full-release-gap-audit.md)。该历史证据不因本次范围调整而删除或改写。
- 本轮双库真实受控查询前置的原始矩阵与结果继续保存在[原验收记录](2026-10-08-controlled-query-live.md)和 `.reviews/controlled-query-live-20261008/run.log`；该记录保持其执行时的历史状态，不代表模型调用、HTTP、角色、阶段事件或报告闭环验收。
- PostgreSQL 的受控真实模型链、数字/evidence/report/run/owner 一致性、风险与安全边界仍须按完整计划验收。AS-04～AS-15 中其余适用门禁也保持原要求，包括角色/报告、结构化阶段事件与回放、调度，以及 PostgreSQL 应用库重启恢复。
- 固定内部角色能力与服务端接线当前冻结待主会话审查；结构化阶段事件验收尚未完成。Phase 6 与 AS-01～AS-15 完整发布仍为 In progress。

专用 MySQL fixture 已停止以释放运行资源；容器、独立卷、网络、DPAPI 凭据和历史证据均保留。准确容器标识、当前状态及可选恢复步骤见 [fixture 安全状态记录](../../.reviews/controlled-query-live-20261008/postgres-only-scope-20261008.md)。

本次范围记录只做文档与目标容器状态核对；未重跑 oracle、adapter、模型或其他验收。
