# 耐久查询证据与 Gateway 固定 JSON 产物接线

你是 `gpt-6-luna` / max 后端 bridge 唯一实施者，主会话负责方案与独立审查。先读根/backend/analytics/Gateway/runtime适用AGENTS、决策0005及本提示词。用户已恢复完整发布任务，本切片使成功查询 evidence 从已完成的SQL repository接到真实analysis运行、结果文件及报告复核，不实现下一切片的模型角色/数字口径核验/阶段事件。

耐久foundation已完成并独立接受：domain AnalyticsQueryToolResult+成功全校验，application StoredAnalysisEvidence+AnalysisEvidenceRepository，SQL repo/codec与0003 migration。每run最多20结果、合计16MiB，exact principal/thread/run；query artifact path已经固定为 `/mnt/user-data/outputs/query-result-{run_id}-{evidence_id}.json`。保留这些不变量和已有59项有效证据。

## 冻结最小接线设计

1. **复用现有 server-owned evidence collector context key 和 RunContext 字段**，不新增通用 file writer、visible tool、身份payload或新的Harness上下文能力系统。原 `AnalysisRunEvidenceCollector` 同步API和旧单元测试保持。新增 App agent `DurableAnalysisRunEvidenceCollector`（可置于独立 evidence_bridge.py）作为其子类，加入精确scope、repo、固定artifact能力及有界async记录/解析方法；Gateway发行这个耐久collector。报告路径要求耐久collector，不能降级为旧memory collector。
2. 使用已有application repository，不把 SQLAlchemy、codec/driver直接import入agent。新的 Gateway 文件能力（analysis_query_artifacts.py）固定 owner/thread/run，只能写/核验 StoredAnalysisEvidence对应文件，不接受调用方任意路径或自由JSON。内容是 `canonical_json(result.to_payload())` 的UTF-8 bytes，先执行domain成功验证，预算上限与foundation一致。凭据、SQL、plan token不在artifact；结果值只在owner隔离artifact/耐久证据，不进入新的平台日志/事件。
3. 文件create-only、完全相同字节幂等、不同内容冲突不覆盖。复用当前 analysis_report_writer.py 的已验证安全模式：outputs目录scope/resolve、专用staging、完整暂存fsync+原子hardlink、symlink/特殊文件拒绝、逐字节安全核验、run_file_io隔离阻塞。可复用已有安全matching helper，但不要为此引入大规模通用IO框架或重构报告writer。file verify必须只检查固定期望文件，缺失/异文/symlink一律失败，不能从任意artifact恢复证据。
4. 记录順序：成功 result全校验 -> 构造StoredAnalysisEvidence -> repo.put -> 固定file.write -> 原collector登记；任一失败只返回稳定 ANALYSIS_EVIDENCE_UNAVAILABLE，不向模型返回成功evidence或artifact回执。文件与SQL库不声称分布式原子事务：repo可能在file失败时留下不可用记录；后续解析必须再次验证固定file与记录字节，不能以数据库有行当成功。传播取消，无宽泛except吞CancelledError。repo/file能力错误不得泄露原异常文本。
5. 报告解析使用 repo.get_many 精确当前scope，并验证每个返回记录的owner/thread/run、requested evidence IDs顺序和完全一致的固定file。整体失败，不部分复核。可补缓存，但持久repo+file是最终可信依据，不从模型messages/checkpoint自报evidence恢复，不接受client任意source_run_id。新耐久collector对象重建、同run/同scope repo+file保留后，应能解析原结果；跨owner/thread/run均拒绝。此切片不声称旧run自动恢复，AS12的server-provenance continuation留后续。
6. query_business_data 对analysis受注入的collector使用async耐久记录。若持久analysis上下文存在但collector缺失/旧memory类型/错scope，**数据库调用前fail closed**；普通chat未携带analysis模式/collector时保持原str行为。成功analysis query返回现有ToolMessage语义及固定artifact state：优先沿用 reports.py 的Command+当前 tool_call_id+artifacts update模式，内容仍是model可读的规范result JSON。没有有效tool_call_id时fail closed且不得执行数据库（Gateway真实tool调用提供ID）。query失败不发布artifact。不要通过把path塞入敏感tool回执来规避已有SSE/history投影。
7. reports.py要求耐久collector异步解析成功快照，然后沿用现有bounded Reviewer、create-only report writer与PublishAnalysisReport。旧memory collector不再满足真实analysis发布门禁，相关synthetic fixtures用真实repo/固定file或最小等价可信capability构造，不能保留生产memoryfallback来迁就tests。
8. Gateway services.py创建run能力时，要求当前 AnalyticsServices.analysis_evidence_repository存在并实际支持端口，missing repo/factory错误均analysis_mode_unavailable、不进普通graph。发行固定file能力和耐久collector后放入现有RunContext.analysis_evidence_collector。既有strip context/config/client能力覆盖与terminal清理继续成立，不新增client可自报的信任字段。普通chat admission不要求repo。

## 所有权与并行依赖

本Agent可改 analytics agent/{evidence_bridge.py,tools.py,reports.py}、Gateway新query artifact能力及services.py、直接相关backend tests、Analytics/Gateway AGENTS的bridge段、独立 `docs/acceptance/2026-10-08-durable-evidence-gateway-bridge.md`。如果确有必要可小范围导出新class；保持现有foundation API不变。禁止改 metric catalogs/management/API/0004/tests、frontend、docs/current-capabilities、总PROGRESS/INTERRUPTION、0005 ADR或部署/真实用户数据。另一个Agent独立接前端metric授予；此前metric后端review-test也独立执行，不碰它的文件。

## 验证 V3（安全/持久化/Gateway边界，限定受影响链）

先补可执行回归：成功/合法零行/截断落库+固定artifact+Command；repo写失败/file失败或冲突不发成功回执、不调用Reviewer/发布；同run重建恢复且跨scope拒绝；symlink/pathescape/特殊文件拒绝；report持久解析后能正常复核/发布；缺repo或client伪造collector analysis启动前拒绝；ordinarychat unchanged；analysis可见工具仍恰三。

实现连贯切片后跑上述新用例及受影响现有 analytics agent tools/reports/reviewer、report-file/新query-file、Gateway analysis admission/cleanup、tool allowlist/模块边界测试；用 rg找实际test names。Ruff check/format/diff直接文件。只在真实失败证明影响时扩展，不重跑无变化的foundation59项或整仓全量。不构建/启动/重启Docker，不调用付费模型、不读真实artifact正文/SQL/结果/secret。

交付实际diff、明确命令通过/失败数、取消与孤立记录/恢复边界限制。不得自称AS07～12完成；这是完整发布链中的bridge切片。冻结后主会话独立审查。
