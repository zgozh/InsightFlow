# 耐久证据基础：独立审查的最小修正

执行者 `gpt-6-luna` / max。主会话已读foundation应用record/repository/codec/migration/test/接线接口；scope SQL过滤、事务预算/幂等、增量迁移与既有通过证据可保留。先修下述确认缺陷，不重写仓储或架构。

## 主会话实际复现

1. 用纯合成 `QueryExecutionResult(columns=('id',), rows=(), row_count=0, byte_count=合法canonical长度)` 建成功evidence，再构造 `AnalyticsQueryToolResult(code='executed',...,evidence=e)`，真实exit1：`rows and evidence must be provided together`。零结果合法且有确定性evidence，当前 bool(rows)==has_evidence 不成立。正常“无符合条件的记录”不能变成内部错误。
2. 合法单行payload只改rows为另一数值、保留旧摘要，`decode_analysis_evidence_result(...,payload_version=1)`真实返回成功；主会话输出 `codec_accepted_mismatched_digest=True`。repository的Stored record外层会拒绝，但codec作为基础公开函数不满足“严格成功结果codec”，下一artifactbridge直接decode存在误用风险。
3. Stored record当前检查code/bytes/hash但没有禁止success evidence的HIGH/BLOCKED风险。V1这种风险永不执行；请用合法重算digest的HIGH/BLOCKED成功fixture实际先证实RED，随后拒绝，不能只凭hash一致就持久化。

## 最小方案与独占

独占 `domain/evidence.py`、`application/evidence_ports.py`、`infrastructure/persistence/evidence_codec.py`、必要 `agent/evidence.py`显式导出、直接durable/evidence tests、foundation原acceptance/Analytics指南说明。不改仓储事务/迁移/composition/SQL策略/前端/其他状态文档，不部署/模型/真实库。

- ToolResult基础类型允许合法成功零行附evidence；“有行必须有evidence”的保护保留，普通失败无行无evidence保持。失败码附evidence、truncation与决定码不一致等由成功结果验证拒绝。
- 把record中对成功结果的公共纯校验收敛为domain函数（如`validate_successful_query_result`），供Stored record与codec encode/decode复用。仅因为这两个边界需要同一成功不变量才增加此函数，不建genericframework。验证固定successcode、LOW/MEDIUM、scalar/row/column/byte硬界、row_count/truncation/decision/resultdigest/evidencehash一致。零行也做完整校验。
- codec先执行现有bytes/严格JSON键/版本/类型检查，再domain成功校验；encode也要拒绝不一致DTO。Stored record继续独立identity/path/time校验，调用同一result校验，不保留重复大段逻辑。稳定错误不回显payload/SQL/identity。

## 验证（V2定点）

回归RED先证明empty success、codec改rows/摘要/bytecount、HIGH/BLOCKED。GREEN直接跑 `tests/test_analytics_agent_evidence.py`、`test_analytics_durable_evidence.py`、必要依赖边界；维护坏响应/无evidence行、序列化输入键与摘要算法既有保护。实际SQLite空结果存取往返可使用已有repositoryfixture，不启动服务。原迁移/预算/concurrency通过证据未受影响，不重跑。

受影响ruff check/format--check与diff；报告更新原foundation记录，说明初始83pass/1fail和44修复证据的适用范围、这次额外缺陷和准确checks，不宣称Gateway已接线。够证据立即实施，约60秒实际进度；完成冻结交主审，不commit/push。
