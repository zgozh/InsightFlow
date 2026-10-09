# 普通账号 PostgreSQL 真实分析正例

gpt-6-luna/max。只有主会话确认guard正式无ExecuteOnce预检通过并审查CJS后才执行。本任务用户已授权完整发布实测，不需再次确认模型调用。所有权为runtime-probes自己的执行输出/必要fixture修补以及 `docs/acceptance/2026-10-09-postgres-positive-analysis-live.md`；生产源码/其它startup文件/原29384/其他项目不动。

新项目iflow-final-pg-20261008，唯一入口127.0.0.1:29388，Gateway sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63，Frontend sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c。四服务/应用PG迁移/checkpointer/Gateway内业务verify_full已通过，证据保留，不重建/重启/重跑它们。

使用已准备run_analysis_runtime_probe.ps1 -ExpectedGatewayImageId... -ExpectedFrontendImageId... -ExecuteOnce。一套新合成adminA/normalB，DPAPI存密码；只登记这套fixture的PGsource/model/policy/revenue metric并显式授权B，不给原真实用户改权限。按照CJS已有严格gates验证目录、匿名/普通admin拒绝、一次deepseek-flash NL分析、实际SQL/Data/Writer/Reviewer链、数值3901.25与三个月份值、query artifact/report、阶段live和durable匹配、浏览器刷新回放/报告/审计。

运行claim是单次发模型闸门，存在则不得删后自动重发。若在claim前遇到实际API fixture字段/路由/状态差异，读直接契约做最小fixture修复并验证，不改生产以迎合fixture；claim后失败保留run/evidence/hash/count/稳定code并交回Principal，禁止盲重复付费call。语义不同不能改断言放宽。CJS先获取完整SSE再比对不证明网络断线重连，对已验证范围如实描述。

日志只safe状态/数量/hash/稳定code；禁止打印请求密码/模型凭据/SQL结果或完整SSE/body。合成report/source正文可内存按oracle核对，不把未知币种当已验证单位。仅合成账户数据可以保存必要opaque thread/run/report/evidence IDs到本目录私有运行上下文，供后续调度/恢复复用；它们不含密码/SQL/结果行。无需重复其他有效unit/前端suite。

这是V3真实用户主链路，成功要有actual report与correct数值/owner、工具与阶段顺序、SSE/durable对照、HTTP/index/preview/download/browser evidence，不能只run success即通过。完成冻结exact调用/结果/剩余边界。AS04/05完整安全矩阵、AS08失败/取消/预算、AS11调度、AS12重启/续跑仍须下一切片，不虚报整个AS01～15完成。
