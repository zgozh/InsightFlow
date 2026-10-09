# 耐久查询证据基础：领域契约、SQL仓储与增量迁移

执行者：用户指定 `gpt-6-luna` / max。先读根/backend/analytics指南与ADR0005。本切片是完整发布计划里程碑2的基础，不因本切片完成停止整体；不宣称AS07/10/12完成。

## 已有事实与职责

现有 `agent/evidence.py` 前半的 `AnalyticsQueryEvidence`、`AnalyticsQueryToolResult`、规范JSON/digest/EvidenceError只依赖标准库/domain；后半`AnalysisRunEvidenceCollector`用Lock缓存run内20份/16MiB结果。基础DTO现在位于agent层，infra不能反向import它，因此把纯证据契约移至domain（如`domain/evidence.py`），collector继续agent；为了既有工具/测试模块接口，agent/evidence显式导入并重导出现有公共名字可保留。这不是无关重构，而是仓储合法依赖的必要迁移；不要移动collector或引入Harness dependency。

独占：domain证据模块及必要domain/__init__；application的证据repository端口/record；agent/evidence纯DTO迁移与重导出（不改collector行为）；infrastructure/persistence证据codec/repository、models.py、新增迁移0003、composition新增服务属性及直接测试、analytics/AGENTS持久证据说明、新报告 `docs/acceptance/2026-10-07-durable-query-evidence-foundation.md`。不改Gateway/Lead/tools/reports/frontend、旧revision/config/globalPROGRESS或其他acceptance。没有模型/部署/旧数据库写入。本轮保留全部已有diff。

## 冻结数据契约

`StoredAnalysisEvidence`不可变值：`principal_id`、`thread_id`、`run_id`、成功 `AnalyticsQueryToolResult`、固定 `artifact_path`（唯一推导值）、`created_at`（UTC aware）。evidence_id来自result evidence，不接受另一个可不匹配ID。线程/run与现有安全ID约束一致，principal非空且非default。路径精确 `/mnt/user-data/outputs/query-result-{run_id}-{evidence_id}.json`，不能接收模型指定路径。record仅允许 executed/result_limit_reached；code/evidence decision、row_count/truncation/bytes/digest及evidence hash相互一致。列/行/标量必须有界合法：领域结果硬界沿用MAX_QUERY_ROWS/结果列256/快照16MiB、NaN/Infinity/未知类型拒绝，不调用任意对象repr/str。

record/codec使用既有JSON结构与engine_cost Decimal规范字符串，不能偷偷变evidenceID算法或ToolResult payload。规范化结果快照bytes按columns+rows计算。完整payload设置明确上限（快照16MiB加有限metadata余量），读取先按UTF8 bytes拒绝过大，再parse/严格键和版本校验。codec未知字段、bool冒充int、损坏/不一致hash、错误risk/status全部失败，不回显payload。

application端口 `AnalysisEvidenceRepository.put(record)` 与 `get_many(principal_id, thread_id, run_id, evidence_ids)`：put同身份同ID同内容幂等，内容或路径冲突稳定error；get_many只在精确owner/thread/run SQL过滤下读，最多20项、不重复、缺一/坏一整体不可用，顺序跟请求，绝不返回别的身份。稳定 `AnalysisEvidenceStoreError` 不带数据。

## 表与事务

新增 `analytics_query_evidence`：复合PK `(principal_id,thread_id,run_id,evidence_id)`，payload_version、payload_json、snapshot_bytes、artifact_path、created_at；限定success数据由domain/codec保证，snapshot_bytes非负CHECK，PK可服务exact-run过滤。不得加Harness user/thread/run FK、SQL或credential列，原七表/历史revision不改。

每run最多20份、snapshot_bytes sum最多16MiB。put在一个短应用库事务中先获取写串行化，再查重复与预算、插入、commit；借鉴现有SqlExecutionPlanStore的SQLite BEGIN IMMEDIATE与PG advisory_xact_lock（证据锁使用自己的key/namespace，不与plan/bootstrap复用），不使用进程内Lock/字典代替数据库容量边界。相同幂等记录不重复占预算，失败rollback；DB异常只映射稳定error。不可覆盖已登记结果。

Alembic新增0003追加建表/索引，down_revision为现有0002_analytics_analysis_reports。迁移显式DDL，不引用动态当前metadata改写历史；upgrade head已有无证据旧库数据保持，新空库能建立，downgrade只删新表。迁移/ORM drift测试的既有固定表集合仅按新表扩展，不放宽检查。

composition在build_analytics_services复用既有shared session_factory构造repository；对原工具兼容不需要此slice就强制query/report调用仓储。新增服务属性如需默认None以保持尚未绑定新bridge的既有测试/普通API构造，解释这个过渡并在下一bridge的analysis admission fail-closed要求实际repository，不创建第二库/隐式memory实现。

## 验证（V2/V3局部持久化边界）

回归优先：实际RED证明仓储不存在/不能恢复。必要长期覆盖：scope拒绝/批量全或无、写入同内容幂等和冲突不覆盖、预算容量/并发至少一次竞争、损坏/未知版本/非法数字拒绝、同SQLite文件不同engine重开仍读取一致；既有evidence digest/toolpayload与collector测试保持。新增迁移test证明0002有数据→head不丢旧record、新空库→head、模型/schema匹配。

只跑直接证据/domain/collector、仓储/codec/迁移/Analytics依赖边界与composition相关测试；影响明确再扩，不跑全backend/前端。用现有 backend/.venv/Scripts/python.exe，不升级依赖。真实PG在后续双DB里程碑加本仓储竞争/重启，不要为此slice提前启动其他service；本次如只SQLite通过就如实记PG未实测。受影响ruff check/format--check、diff review。

每约60秒报告实际已编辑/RED/GREEN，够接口信息马上实现，不耗时全仓历史/长架构复读。最终精确文件diff、命令/退出码/数字与剩余接线工作；不commit/push、不得宣称query已写artifact或真实恢复验收通过。主会话独立审查后自动派Gateway/toolbridge。
