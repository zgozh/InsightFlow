# 真实模型请求前的已确认 oracle 修正

gpt-6-luna/max。身份runner已被Principal独立无ExecuteOnce复验accepted=true；该PS文件不再修改。只改runtime-probes/analysis_runtime_probe.cjs的下列确认缺陷和准备验收记录，绝不执行API/seed/model。整体positive执行需等此次冻结独立审查。

1. monthly oracle 当前actualValues为String数组，调用无comparator的sort()，却比较数值排序的expected数组，必定把正确数据报失败。改为严格按period->revenue映射核对 {2026-01:1200.50,2026-02:1800.00,2026-03:900.75}，保持三行/唯一period/数值规范化与scope/digest checks。不放宽断言；不靠排列正确值忽略对应月份。
2. 当前artifact.columns.every只允许源列名会误拒绝合法SUM(revenue) AS total_revenue之类派生输出。禁止description/customer_email仍保留，允许安全派生结果列；表级/列级授权由真实query pipeline实施，不能把结果alias whitelist当授权证明。monthly oracle明确需要period/revenue原列；新增SUM合法alias场景不能被错误失败。现有scope、checksum、closed evidence fields不改。
3. ANALYSIS_PROMPT应明确本正例需要生成并发布经营分析报告，逐月period/revenue与合计，显示保留两位小数，不能推断币种/物理单位。当前prompt只要求列出/合计，却断言必有published report，场景和要求不一致。仅对齐用户动作/验收，不改模型系统提示或生产代码。

V1最小check：Node --check、直接oracle小fixture正例与月份错配拒绝（可用私有纯函数或简单离线片段，不运行CJS main），确认合法sum alias与禁止字段边界。不要加新测试框架/全应用suite。Domain evidence.engine_cost为canonical decimal字符串，当前fixture rows是numeric->字符串，canonicalJson hash校验保留，不引入跨语言重序列化框架。保持日志safe，不读取实际密码/凭据。冻结exactdiff/checks后交回。
