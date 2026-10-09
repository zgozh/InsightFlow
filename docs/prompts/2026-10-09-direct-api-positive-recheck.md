# 最小更新后直接重测分析API

gpt-6-luna/max。主会话已独立审查五处固定日志、缓存标记测试修正；22项角色测试与两文件静态检查通过。现在直接推进真实API，不再切碎排查，不跑大套测试。

所有权：`.reviews/final-postgres-runtime-20261008/` 中本切片独立构建/部署/重测脚本与证据、`docs/acceptance/2026-10-09-direct-api-positive-recheck.md`。生产源码不改；原claim/原失败证据保留。只操作新29388项目，旧29384与其他项目不动。

1. 用已存在 Gateway 镜像 `sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63` 作 FROM，仅 COPY 当前 roles.py 到镜像内同一实际源路径，不重装依赖、不apt、不拷全目录。先确认基底文件路径；保存本次source hash与新image ID，旧image保留回滚。
2. 仅更新既有 gateway 服务，复用现有runtime.compose.yaml、卷/网络、当前认证secret和server配置。不要重跑初次Apply/生成新auth token导致前端失配。敏感env仅内存从已有受控材料或容器解析，任何输出只能服务状态/ID/hash/计数；不打印env、完整compose、DSN或密码。不重建Front/Redis/PG/Nginx。更新前确认精确项目/原Gateway容器/镜像；若既有helper无法安全复用，先报告具体约束，不盲改。
3. health/readiness与镜像确认后，使用同一合成B和既有合法夹具，直接执行一个新分析run。这次重测有代码诊断更新依据，允许**一次新run**，但必须有独立新claim（如positive-model-run-diagnostic.claim），不删除/覆盖旧claim。复用既有探针业务断言，不重新写整套框架；新thread/run opaque IDs在创建/返回时立即保存ignored私有context，终态/阶段失败均即时保存，不再丢ID后枚举恢复。新runner期望新Gateway hash，Front实际hash直接读取核验。
4. 成功核对3行月份与3901.25、报告/证据/阶段/owner API，继续现有probe的页面断言；若失败，只提取Gateway本次运行时间窗的固定 `analysis_data_parser_rejected.*` 枚举日志及既有stage稳定码，禁打印其余日志/模型SQL正文。不要再发第二次模型，定位具体拒绝分支后交回。
5. 短记录实际commands/status/checks/newimage/仅Gateway更新的证据，立即冻结。不要扩展archive manifest、文档清理或其它场景。

V3运行更新与单条用户主链路。无需重复已有效的22tests/build；只有本次网关health/readiness+真实API以及失败时固定原因枚举是新增证据。
