# 数字引用与确定性计算：纯领域基础切片

完整发布任务继续，Gateway/Frontend已由用户更新（当前只待原Nginx手动补启动及真实验收）。现有query evidence foundation与bridge已接受，别重写。AS10仍缺通用数字引用/计算核验；本切片只实现纯领域数字合同，后续角色/报告接线另行冻结，不新增服务/模型/数据库/API。

由 `gpt-6-luna` / max 实施，先读 backend/app/analytics/AGENTS domain边界与本提示。唯一生产文件 `backend/app/analytics/domain/claims.py`，可按已有风格从 domain/__init__.py 导出；唯一直接测试 `backend/tests/test_analytics_numeric_claims.py`，必要时仅修改domain stdlib allowlist以加入真正使用的stdlib（decimal原应已允许）。唯一记录 `docs/acceptance/2026-10-08-numeric-claim-domain.md`。不得改Gateway、roles、tools/reports、metric/API/DB/frontend/部署脚本/总PROGRESS/INTERRUPTION，不派Agent或调用模型/真实数据。

## 最小冻结合同

1. 不可变/slots `EvidenceCellReference(evidence_id,row_index,column_name)`：evidence ID 64小写hex；row_index非bool整数>=0；column_name非空且有界（与现有结果列名约束一致），不接受SQL/path/自由表达式。
2. 不可变 `NumericClaim(id, operation, operands, value, decimal_places, unit_reference=None, period_reference=None)`。id为有界唯一slug；operation闭合 enum：cell、sum、difference、ratio、percentage、mean、change_percentage。不eval任何用户表达式。operands是有界tuple cell refs，cell恰1、difference/ratio/percentage/change_percentage恰2、sum/mean1～50。value是有限有界十进制字符串（不允许NaN/Infinity/指数/无限位数）；decimal_places为非bool0～12。
3. 纯函数 `verify_numeric_claims(claims, snapshots)` 输入不可变tuple（<=50claims、<=20成功AnalyticsQueryToolResult），构造exact evidenceId索引；重复claim id/歧义snapshot id/失败或坏digest snapshot都整体拒绝。复用现有 validate_successful_query_result，不信DTO实例类型，结果快照合计16MiB预算沿用现有契约。每个ref必须在snapshot中找到确切唯一列名与行，不能扫描“任意数字在任意结果出现”。重复列名应视引用歧义拒绝，未知/越界引用整体失败。
4. 数值来源仅int/finite float/规范十进制str，bool/None/任意对象拒绝；保留十进制精度，使用局部有界Decimal context，不能修改全局context，不将Decimal转float算账。限制输入/结果位数和指数，避免极端值资源消耗；正确处理零/负数，分母为零失败。固定算式：cell=value；sum加和；difference=a-b；ratio=a/b；percentage=a/b*100；mean=sum/len；change_percentage=(a-b)/b*100。显示按ROUND_HALF_UP与声明decimal_places，asserted value须与确定性显示值数值相等，不能容忍误差或因模型Reviewer同意就放行。
5. 返回不可变 `VerifiedNumericClaim` tuple，含id/op/来源refs、服务端计算的decimal字符串、rounding标记、是否引用truncated快照、已解析unit/period标签（有来源才可有值）与原source引用，字段取最小必要集。未提供unit/period source时返回None，不能猜元/月/百分比。给定unit/period reference必须是同一批合法成功快照里的确切单元格，其值必须是有界无控制字符的非空文本（period可支持规范年份整数，但必须明确定义、不可任意str对象）；禁止直接自报无来源unit/period字符串。这里仅证明标签来自已绑定结果，不证明该查询业务语义/物理单位或期间过滤正确，报告必须如实注明该界限。
6. 固定稳定 `NumericClaimError(reason)`，任何失败不回显SQL、行值、claim原value或异常原文。bad constructor可沿用ValueError稳定reason；verify入口统一整体拒绝，不返回部分verified。结果始终只表述“这些引用单元格的计算”，不能推断全量业务数据完备，即使truncated=False。

## 验证 V1

有长期价值回归：exact cell、跨evidence明确sum、difference/ratio/percentage/mean/change_percentage、合法零、负数与边界四舍五入、错数字、错/越界ref、歧义列/重复evidence/claim、bool/null/nonfinite/坏decimal、大数预算、zero denominator、坏digest/失败快照、无unit/period不猜测、context exactref与坏ref、truncation标记、全局Decimal context不变。按行为组织参数化，不逐字段机械getter测试。

实现整个连贯切片后只跑新claims测试与domain模块边界定点（不跑既有59/192全量）；受影响Ruff check/format/diff。uv统一 `uv run --no-config --default-index https://pypi.org/simple --locked` 防本机镜像重写canonical锁。命令前后锁不得变化。无需JSON parser/LLM schema/renderer/迁移或图表实现。

交付actual diff/精确检查结果并冻结。记录清楚尚未接报告、未完成完整AS10，更不能把本数学基础包装成完整口径证明。主会话据此再制定role/report渲染合同。
