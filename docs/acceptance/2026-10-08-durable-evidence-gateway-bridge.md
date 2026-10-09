# 耐久查询证据 Gateway 接线验收

主会话已独立审查并接受本切片的源码接线边界。本切片将已验收的 Analytics evidence repository 接入真实 analysis run；未部署，固定分析角色、数字口径核验与阶段事件仍未完成。它不改写 foundation 的 domain、codec、SQL repository 或 migration。

Gateway 只在读取 owner-scoped 持久线程的 analysis marker、确认认证 principal 与 run owner 一致，并确认当前 `AnalyticsServices.analysis_evidence_repository` 提供 `put/get_many` 后，才允许 analysis run 进入图。它向当前 worker 注入绑定 principal/thread/run 的 `DurableAnalysisRunEvidenceCollector` 和查询 JSON 文件能力。客户端的 context/config marker 与 collector 仍在 Gateway admission 清洗；analysis 查询还会在计划或数据库调用前检查已清洗的 runtime marker、耐久 collector scope 与当前 tool-call ID。

成功 query 先按 domain contract 完整校验，再写 repository、以 create-only 方式发布规范 JSON 到 `/mnt/user-data/outputs/query-result-{run_id}-{evidence_id}.json`，最后登记旧 run-local cache。相同字节重试可用，异文不覆盖。结果的 ToolMessage 内容仍为规范 query JSON，当前 tool-call ID 用于关联，artifact path 只进入 `artifacts` state。普通聊天没有 analysis marker 或 collector，继续返回原有字符串结果。

`write_analysis_report` 不再接受 run-local memory collector 作为证据来源。它按当前 principal/thread/run 和请求顺序重新读取 durable records，并逐条核验 repository 返回的身份、固定路径和文件字节；缺失、损坏、异文、跨 scope 或文件 symlink 均整体失败，Reviewer、报告文件和索引都不会继续。repository 与文件系统不是分布式事务：repository 写入成功但文件发布失败时可能留下孤立行，之后的报告解析仍会拒绝该 evidence。

验证范围为 V3，覆盖持久化恢复、固定文件边界、查询/报告及 Gateway admission 链。首轮定点批次覆盖 Analytics Agent evidence/tools/report/reviewer、报告与查询文件能力、Gateway analysis admission、allowlist 和 analytics boundary，结果为 `192 passed, 2 skipped, 3 failed`；2 项因 Windows 主机无法创建 symlink 而跳过，3 项新增 admission 断言发现稳定错误码不一致。修正后完整 `test_analytics_agent_tools.py` 文件 27 项通过，`test_durable_collector_propagates_cancellation_before_file_write` 定点项 1 项通过。9 个受影响 Python 文件的 `ruff check` 全通过，`ruff format --check` 全通过。此前交接记录未保留这些检查的原始完整命令串，因此本文不重建命令，也未为补记命令而重跑；foundation 原有 59 项证据未重跑。未启动服务或 Docker、未调用真实模型，也未读取真实业务结果或 secret。
