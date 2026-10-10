# 最后一个分析生命周期 fixture 与后端检查

实施者 gpt-6-luna/max，独立上下文。已有前后端worker都已冻结，不与其他实施者并行写文件。当前所有未提交改动属于本轮CI修复，不能回滚或覆盖。读取backend/目标AGENTS及本说明即可，不复读全仓历史。

## 已完成与剩余

fa0213c GitHub后端17失败已定位并修改，前worker精确批次14pass/2个Windows requires_safe_capture skip/1fail；RunJournal run.end内存消息类型与Memory/JSONL/SQLite敏感投影回归已过。前端1过时Galaxy源码测试移除、8文件纯格式也已过。主会话已独立审查production journal.py/serialization.py与主要fixture差异，接受安全投影保留策略；不重测已有效证据。

剩余 backend/tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get。fixture从旧ephemeral collector与FakeToolCallingModel迁到真实durable collector/owner-thread-run仓库fake/现有 AnalysisChatOpenAI。准入已过，但 run success 时 plan_query.calls=0；当前只patch AnalysisChatOpenAI._agenerate，真实LangGraph lead用astream，绕过该入口走MockTransport空响应。

主会话已读实际helper和测试：优先 create_analysis_chat_model(..., disable_streaming=True) 让BaseChatModel streaming路由回ainvoke，再使用当前 _agenerate 对lead预置tool_calls、其他独立角色用原helper responder。无需改生产代码/全局helper。保留plan/execute各1、report发布、durable collector/snapshot、owner/thread/run、跨线程404和事件脱敏断言。现 artifact.text == report_markdown 也可能过时（新版Data/Writer是服务端根据NumericClaimPlan渲染），须按当前有证据的固定格式/数值/引用核对，不绕过Reviewer或改回未经核验的模型Markdown。

## 所有权与步骤

仅修改上述lifecycle测试及本轮直接受影响后端文件的Ruff机械格式，不新增通用抽象、不写frontend/。需要修确切关联fixture有必要可以修改，但不得松动实际生产安全门禁。

1. 最小修fixture，运行唯一失败node。因sandbox PermissionError按tool规则require_escalated申请，不绕过。模型全本地MockTransport，无外网/付费调用。
2. 成功后对本轮17个backend/root变更中的Python文件做Ruff lint/format；只机械修真正报告的问题。不要本机重跑14k全套或已通过14项。compile/type无需另外加。
3. 写 docs/acceptance/2026-10-10-ci-backend-repair.md，逐条列原4分片17 nodeid根因/修复/实际验证证据，注明本机skip与Linux新CI待验，真实production改动仅journal/serialization。旧日志在 .reviews/ci-20261010/，只看失败summary必要片段。
4. freeze返回actualdiff和检查命令结果、未满足事项，暂不commit/push。主会话独立审查后正常提交，并读取新的全部Actions结果收尾，不关闭/改workflow门禁。

保护uv.lock canonical46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912。可以读既有worker报告证据，但不复读/重跑有效历史检查。
