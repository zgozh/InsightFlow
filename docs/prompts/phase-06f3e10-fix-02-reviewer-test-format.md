# Phase 6F3E10 Fix 02：补齐受影响测试文件的格式门禁

> 执行者：现有 `gpt-6-luna`（max）。这是对 `dda0335` 的纯格式复核，不重做真实报告链路。

主会话只读审查已确认 `backend/app/analytics/agent/reviewer.py` 通过格式检查，但 `backend/tests/test_analytics_agent_reviewer.py` 在 `ruff format --check` 下显示 `Would reformat`。仓库级 `AGENTS.md` 要求受影响文件的格式与静态检查，因此此项需补齐。6F3E10 的 86 项定点测试与两次真实 run 的行为证据仍有效。

仅对 `backend/tests/test_analytics_agent_reviewer.py` 执行仓库既有 Ruff formatter；检查 diff 只含格式变化，不改断言、生产代码、配置或依赖。随后运行该文件的 `ruff format --check`、`ruff check` 和 `git diff --check`；纯格式修改不重跑 pytest、Docker、Gateway、模型或 E2E。单独提交 `style: format reviewer diagnostic tests`，工作树保持干净，把命令/结果简短追加到原 `.reviews/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`。若 formatter 引起语义性变化，停止报告，不自行扩大范围。
