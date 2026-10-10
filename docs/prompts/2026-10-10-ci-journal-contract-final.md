# 新 CI 唯一 journal 断言修正

实施者gpt-6-luna/max，只拥有backend/tests/test_run_journal.py与docs/acceptance/2026-10-10-ci-backend-repair.md追加本次结果。其他writer仅backend/AGENTS长度与ignored部署，不跨写。

1f7639e新LinuxUnitTests run38033361469：shard2/3/4及default collection成功，shard1仅 tests/test_run_journal.py::TestLlmCallbacks::test_analytics_structured_payloads_are_projected_for_journal_events[asyncio] 失败，TypeError Object of type ToolMessage is not JSON serializable。日志 .reviews/ci-20261010/job-114158680148.txt。

主会话已确认run.end的Memory契约应保留BaseMessage，JSONL/DB用既有default=str，SSE/API由serialize_lc_object投影。前fixture安全断言直接json.dumps全部memory events，与已通过类型契约冲突。先读实际测试、契约/serializer确认；改断言使其走真实公开序列化/持久字符串化对应入口，再核对所有原SQL/rows/metadata哨兵仍未泄漏。不能删安全断言、全事件变str看不见字段、skip、改production背离契约。保留其他event原断言。

定点跑失败node及TestLlmCallbacks同类直接关联用例（可同文件小suite，不全backend），Ruff该文件和format check、diff。记录精确结果并追加新CI17旧fail已闭合/剩余本项通过/6Actions仍待最新核验事实，不修改旧历史测试统计。

完成freeze返回actualdiff/checks，不commit/push。Root复审后统一与AGENTS门禁修改一起正常提交，新CI验证。source4py冻结不改，uv.lock不动；当前dangerfullnever不sandbox_permissions。
