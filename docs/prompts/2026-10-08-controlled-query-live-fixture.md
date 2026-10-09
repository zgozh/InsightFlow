# 双库受控查询真实验收前置

实施gpt-6-luna/max，仅验证已存在的生产受控查询用例/真实adapter，不调用模型、不改生产源码。主会话正在等待角色Gateway接线，最终自然语言/角色链会在统一构建后验收，本切片不冒充AS02/03全部完成。

## 所有权与隔离

只拥有新 `.reviews/controlled-query-live-20261008/` 与 `docs/acceptance/2026-10-08-controlled-query-live.md`。只读backend Analytics AGENTS、composition、plan/execute/adapter相关契约及既有测试，按rg定位，不全仓阅读。另一个worker改角色接线生产文件，两者不共享输出。

可复用新建PG fixture `evidence-pg-live-20261008-c0efb9fd03`（127.0.0.1:29386），DPAPI重连资料在 `.reviews/evidence-postgres-live-20261008/`；其原 `evidence_fixture` 数据库与既有证据行不得修改/删除。在它内部建立独立business fixture数据库/只读角色/固定小样本表即可，凭据DPAPI保存、进程内传入，禁止CLI/日志/明文落盘。不能操作29384/29385或真实库。

MySQL仅使用本机已有合适镜像；可建立独立唯一项目/网络/volume，29387或其他确认空闲端口必须显式127.0.0.1；禁止拉镜像/构建。如果镜像/权限缺失，只记录该库阻塞，不换工具绕过。保留fixture供最终角色真实验收复用。检查日志/inspect只能安全字段，不Env/凭据/原始配置。

## V3 实际检查

使用生产PlanAnalyticsQuery/ExecuteAnalyticsQuery与真实PG/MySQL adapter，不直接调用adapter后声称治理通过。可以用本任务独有SQLite应用库、真实analytics repositories与迁移创建合成datasource/schema/policy/metric，principal只合成测试身份；不要把fake catalog/estimate/execute当真实证明。

合成数据oracle例如两期金额/成本/用户统计，两个库具有相同逻辑数据；只读DB账号具SELECT权限，服务端secret resolver返回真实fixture凭据。直接SQL oracle与受控query的结果逐值/类型/列名比较，记录摘要与布尔断言，不输出密码/plan token。至少成功聚合一项、权限拒绝一项（禁列/禁表/别的principal）、计划只使用一次、HIGH/blocked在DB执行前拒绝。

按实际可实现边界补AS06证据：LOW/MEDIUM有效timeout/rows/bytes不同；使用小fixture限额验证真实行/字节截断及结果code/审计；仅有安全可控慢查询时才做真实statement timeout，禁止生成大规模数据/昂贵join或绕过SQL policy。不能证明真实timeout时明确留下该项，不造通过。metadata/audit只允许批准结构字段，检查无fixture SQL/secret/rows/plan token泄漏。

先一个完整可运行slice，再一次检查；生产源码确认缺陷只报告复现和路径，不跨所有权修复。不要跑全套/复验已通过PG evidence链/真实模型。用已有backend .venv，禁止为本任务同步改动其他worker正在使用的依赖环境或uv.lock；若驱动缺失准确阻塞。脚本语法+实际断言命令/退出码、oraclehash/权限/限额矩阵、保留fixture安全重连写报告。

返回哪些AS前置证据已补、哪些真实模型/HTTP/阶段事件仍未覆盖。最终冻结后由主会话审查并在统一构建后的角色run复用同一数据oracle，避免反复重建fixture。
