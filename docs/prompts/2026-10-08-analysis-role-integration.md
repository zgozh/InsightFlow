# 固定内部角色与可验证报告接线

实施 gpt-6-luna/max；先读取适用模块 AGENTS，以及已冻结 roles.py/Reviewer/claims/verified_report 和对应验收记录。只按入口定位相关源码，不读整仓历史。

## 目标与所有权

完成 AS07/08/10 的生产调用链接线，保留已批准分析 Lead 精确三个工具及其模型可见参数：inspect_business_catalog、query_business_data(datasource_id, sql)、write_analysis_report(title, markdown, evidence_ids)。不得重开task/MCP/bash或任意文件工具；普通聊天原有模式保持。

可改：analytics agent/tools.py、reports.py、roles.py（仅下述查询锁/预算与必要接线）、新增 application/metric_service.py；Gateway services.py；Harness constants.py、runtime/runs/worker.py、agents/lead_agent/agent.py；直接涉及的新/已有测试；analytics AGENTS.md 与独立验收记录 `docs/acceptance/2026-10-08-analysis-role-integration.md`。禁止重构Reviewer/domain/persistence/migrations/frontend或修改无关既有改动。Reviewer SDK修补已冻结并独立审查；roles已修正完整schema与SDK无重试，14项定点通过。

## 服务端发行、清洗与关闭

新增一个 server-owned ANALYSIS_ROLES_CONTEXT_KEY（值 __analysis_roles）；沿用既有 Reviewer issuance 路径，在Gateway准入为analysis run创建实际 AnalysisRolesCapability。同一可信身份、thread、run，必须所有能力齐全，否则 fail_start，不降级普通图。

RunContext与_build_runtime_context注入该能力；Gateway body.context/body.config/configurable与worker清洗集合、结束/异常清理全部覆盖新key，客户端不能提供或覆盖该对象，不能进checkpoint/configurable/公开metadata。Lead assembly创建未绑定lead_model时为Reviewer和roles分别 bind_lead_model；角色无法绑定则analysis启动明确失败，不能只log后继续假运行。所有结束路径close角色能力且移除引用，防止callbacks/运行配置长期留存；测试当前worker取消/错误清理边界。

## 受权 Metric Service

新增最小应用级 MetricService，依赖既有 MetricCatalog：读取认证principal的active唯一受权指标，返回 immutable tuple（最多50，错类型/重复/非active/超限稳定拒绝），不是新模型工具或Agent。不要重复实现授权：真实可用性继续由既有catalog/grants决定。保留 expression（登记业务文本，不执行）、dimensions/version供内部角色。目录inspect的白名单投影可补expression字段并同步测试/说明，不暴露owner/secret/policy。

每次query/report按当前principal读取一次immutable目录快照用于该次角色输入。报告冻结该次受权目录的key/version/登记业务定义为独立“可用指标目录快照”来源元数据，不能声称目录所有项已用于算式或由文本证明SQL语义。为空必须明确写“未登记可用指标口径，本报告仅核对结果单元格与固定算式”，不得臆造version/unit/period。元数据使用安全字面code块（四空格逐行缩进规范JSON可避免反引号/HTML注入），只投影公共登记字段，不owner。整份报告最终UTF-8仍≤32KiB；避免重复查询catalog/长期缓存授权。

## 查询链与预算

analysis_mode为true时：先验证durable collector、roles实际类型/identity/tool_call_id及合法参数；读取受权datasource可见性和metrics；在任何模型或DB plan前拒绝缺能力或身份不符。

roles增加run-local serialize_query(principal/thread/run) async contextmanager，用独立query锁串行包住 SQLAnalyst→plan→execute→durable artifact全过程；等待锁后重查scope/closed。每run最多4次开始的analysis query（失败/取消也消耗；与每角色最多2次不同输入调用预算不同），超过稳定attempt_limit且不得调用模型/plan/DB。无递归或隐式重试。

SQLAnalyst.refine_sql以Lead候选sql与受权指标形成真实独立零工具模型请求；返回sql**仍必须**走原plan→execute。原SQL policy、语义授权、EXPLAIN、read-only、单次token、timeout/rows/bytes与durable receipt全部复用，不跳过、不二次执行或失败重plan。模型SQL/结果/异常不进入事件或日志。analysis角色错误仅返回稳定analysis_role_<reason>，CancelledError继续传播。普通聊天的既有查询分支不新增角色调用或query预算。

## 报告链

保留tool参数以保护已批准schema与旧记录解析。markdown现在作为**不可信分析目标/草稿**传给 roles.analyze(analysis_request=markdown.strip())，最多8192字符，不直接发布其文字/数字。更新中文docstring说明服务端重建报告。title同样仅作为请求描述，发布文件/索引采用固定“经营分析报告”，防止列表标题夹带未验证数字；实际报告内容由固定模板生成。

匹配所有server capabilities→durable collector exact-scope完整解析→MetricService快照→DataAnalyst真实调用且 verify_numeric_claims 成功→ReportWriter真实独立layout→render_verified_report+受权目录元数据→现有独立Reviewer→固定文件writer→publish索引。任一步失败不得write/index或返回成功artifact。绝不能退回旧自由Markdown发布。安全工具回执仍只code/report_id/artifact_path/evidence_ids；不新增推理/原始行/角色响应字段。

先做Data/layout/render输入验证再Reviewer，错误稳定脱敏且不消耗后续角色。报告缺单位/期间时显示未提供，截断/舍入提示保留，不能谎称完整业务总体。此链只证明exact evidence+算式与来源标签；SQL业务语义的局限继续明确，不靠模型approved当数学证明。

## V2/V3定点验证与交付

这是身份、runtime wiring和报告发布边界，使用直接受影响工具/报告/角色查询锁/Gateway admission/worker context-cleanup/Lead绑定测试，并检查精确三个tool schema未扩展。复用durable foundation/SDK已有通过证据，除非实际改动其证明面不重复；不跑整仓/构建/真实模型，下一里程碑统一构建与真实验收。

新增关键成功链用本地ChatOpenAI生成double（遵守已冻结SDK形状），证明SQL/Data/Writer/Reviewer独立调用顺序、SQL仍plan一次execute一次、数学失败零写、正常report固定值/单位/期间/来源、空目录明确；恶意草稿数字/标题不得直接发布。证明角色注入清洗、跨owner/thread/run拒绝、缺能力不得DB、4次query上限、并行两调用实际执行串行、取消传播与关闭后禁止。

既有测试受行为有意变更时更新fixture/期望并说明；新发现实现回归窄修，环境/无关旧失败不扩范围。uv使用 --no-config --default-index https://pypi.org/simple --locked，uv.lock不变。pytest/Ruff/format准确命令与分批结果落记录。冻结后交主会话审查；仍不宣称完整AS07/08/10真实验收已通过。
