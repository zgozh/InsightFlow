# 补齐Reviewer的确定性证据映射

gpt-6-luna/max，根/backend约定适用。主会话独立读claims DTO、reports调用、reviewer payload，确定输入信息缺口：已验证数字声明有独立operand/unit/period引用，但renderer把引用合并，reviewer只收到Markdown和原rows/metadata，缺结构化对应。此次不是判定旧拒绝错误，也不能改旧失败记录为成功。

所有权 reviewer.py、reports.py、直接相关 reviewer/reports 集成tests，以及 docs/acceptance/2026-10-09-reviewer-verified-evidence-map.md。roles/frozenmath/renderer/前端/其它生产不动，不模型不部署。V2内部调用边界。

复用现有 VerifiedNumericClaim DTO，由write_analysis_report把Data产出的**server已验证claims**传入reviewer。payload新增一份闭合映射：claim id/operation/calculated_value/source_references/unit/period/unit_reference/period_reference/rounded/truncatedflag。不新增模型可见工具参数、API契约或客户可注入context。所有reference按当前允许snapshot/evidence IDs范围核对，boundedclaims/count/bytes；声明必须来自当前run server验证路径，不能把模型自称verified或任意dict当证据。选择最小实现在现有reviewer方法内收敛，不新wrapper框架。

提示明确：successful_queries rows是源数据；verified_claims给出确定性算式与引用对应；元数据ID/hash/版本/行号/条数、登记指标定义是溯源/口径信息，不是经营结论，不能拿它们当未证实收入数字；不能因标签被固定安全操作名替代或单位“未提供”就臆造不一致。同时仍检查实际数字/期间/单位/证据引用矛盾、不受支持结论，任何不匹配仍failclosed；不能自动批准、忽略LLM reject或增retry。

缓存fingerprint必须绑定新映射，禁止同markdown+evi但不同map借用旧decision；输入byte总限/角色次数2/sdkzero/callback隔离保持不变。legacy直接调用如无map能继续原review合同可用，但受控发布路径必须有map；优先最小默认tuple参数避免无关调用批量改，仅关闭控制发布的缺map路径。不能为compat引入复杂分派。

回归：报告工具实际把verifiedData DTO传给reviewer；模型收到引用角色/值metadata明确区分；坏shape/错scope/map与source明显不一致拒绝，不跨缓存，inputbytes依旧有界；模型reject仍拒绝且无publish。复用现有fixtures，只跑直接reviewer/reports受影响文件（角色39tests不变不重跑）及改动Ruff。交actualpatch/checks冻结，Principal独立review后部署再一次有输入改进依据的scheduled正例，当前不得自行模型。
