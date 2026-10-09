# 展示标签修复后真实API验收

实施 gpt-6-luna/max。主会话独立审查 _parse_data_result 补丁：只替代不合规展示文本，ID集合与数值引用验证原样保留；35个相关测试和静态检查通过。现在直接推进一次有明确修复依据的真实API，不继续离线排查或重复测试。

所有权：`.reviews/final-postgres-runtime-20261008/` 本切片单文件镜像更新/新claim runner/证据，以及 `docs/acceptance/2026-10-09-label-repair-api-acceptance.md`。原roles.py修复记录可补精确35项tests命令结果，不改其他生产代码/前端/README。

完全复用上轮已成功的最小COPY构建与仅Gateway compose更新流程：基底c5a7a0c535ff06fe680b4f0a04304beed3c839f940bbdfa0825e0e213e96d3da加本地tag，COPY当前roles.py到已确认路径，保留认证secret/应用数据/网络/其余3个容器。不要再尝试FROM裸sha256或漏DEER_FLOW_SKILLS_PATH；直接复用已有deploy脚本/环境内存材料。保留所有旧image及两次claim/evidence，禁止重建依赖或整栈。

健康与镜像校验后，使用同一合成B/治理夹具，一次新run，独立claim `positive-model-run-label-repair.claim`、独立evidence/context文件名。复用现有诊断runner业务断言，保存opaque IDs不回扫历史。核对真实报告数字、阶段、证据、owner API与浏览器；如果runner在成功run之后失败，先检查同一次run的已有产物而不是再发模型。

若业务仍失败，提取本次固定parser reason和既有阶段稳定code后立即报告，不重新调用。若业务成功、仅探针不匹配真实合法response，核对实际契约做最小探针修复并**只读复验同一run**，不得改产品去适配测试。

V3：Gateway health/readiness与该单次真实主链路即可。写短验收结果、命令/newimage/旧服务保持证明、精确剩余边界并冻结。不要进行与该链路无关的archive/metrics重建/文档清理或大量门禁。

最新只读续验裁决（主会话已读现有CJS）：成功run已生成1份published报告，四个数值匹配，预览200。CJS已有 READ_ONLY_RESUME、prepareExistingAccountsReadOnly、readExistingDatasourceReadOnly、createAndRunAnalysis(..., resumeContext) 与成功阶段链函数，**不要再新建helper或node -e**。只把main接通：只读模式要求原claim与私有context存在、跳过原claim拒绝、登录既有账号、读取精确datasource、verifyUserCatalogApi/inspectBrowserCatalogs后createAndRunAnalysis(...,context)，完全跳过seed/create分支；正常模式原样。finally的证据路径只读时使用已定义RESUME_EVIDENCE_PATH，不覆盖原evidence。

PS1仅加 ReadOnlyResume 开关：原 ExecuteOnce gate在非只读模式维持，传node固定参数 --read-only-resume-existing-run；不变更身份guard/凭据输入。保持UTF8BOM。node --check后直接用 -ReadOnlyResume 跑一次真实同一run续验，禁止新模型。遇到真实契约差异定点修fixture并只读续验；任何失败先报告具体stage/code，别长时间无动作。补齐该文件已有的report artifact/audit/preview/download/browser检查后冻结即可。

最新审查：续验已通过API产物、scope/月度oracle/摘要、审计、报告下载同体、成功阶段链；仅 currency正则可能把固定展示词“引用单元格”的“元”误认币种。生产renderer明确表头含单位列，未知unit应为“未提供”。先内存核对误判来源，报告仅安全布尔；随后探针严格解析现有六列报告表的单位列，要求所有数据行该列为“未提供”，保留对明确货币符号/美元/人民币等的拒绝，禁止裸匹配整篇的汉字元。解析需拒绝缺表/错误列数，不能静默通过。不改生产。

只读续验没有live流，live_and_durable_stages_match不要写成false误导成不一致，也不能写true冒充验证；用本检查未复验的明确状态或省略该check，并在记录说明。修fixture后直接同一run只读继续browser；不得新模型或再造helper。
