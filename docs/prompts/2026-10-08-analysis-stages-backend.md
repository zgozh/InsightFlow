# AS09 阶段事件服务端生产接线

gpt-6-luna/max。读取适用AGENTS与已冻 `contracts/analysis-stage.v1.json`、阶段路由取证记录、角色集成记录。角色生产接线已被主会话审查：scope、query锁/4次预算、16步上限、确定性报告和能力生命周期接受。当前PostgreSQL必验、MySQL可选。

## 所有权

新 analytics/agent/stages.py、对应测试；必要的 roles.py/tools.py/reports.py；Gateway services.py 与 routers/thread_runs.py；Harness runtime/runs/worker.py（不得import App模块）、runtime/events相关文件仅确实需要时；analytics AGENTS.md；独立验收记录 `docs/acceptance/2026-10-08-analysis-stages-backend.md`。domain/verified_report.py仅允许下面一处表头V0文案，不改算法/DTO。不改合同/数据库schema/前端/其他fixture。另一个worker独立改frontend消费者，双方只依赖已冻合同。

## 冻结通道与持久映射

SSE仍 `event: custom`，data为完整analysis_stage payload。调用既有aemit_custom_event，不改成新SSE事件名，不向阶段事件塞原SQL、结果行、provider文本、secret/DSN、plan token或CoT。

永久记录使用既有RunEventStore.put：`event_type="analysis.stage"`、`category="analysis"`、`content=""`、`metadata=<完整contract payload>`，thread_id/run_id来自服务端绑定。Record.seq是thread全局游标，metadata.seq是独立per-run阶段游标，不能互换。GET /events保留现有record结构，仅为此event_type按合同投影metadata；不加data字段、不改endpoint，不扩大其他metadata权限。

服务端run-scoped emitter绑定principal/thread/run，从可信Gateway发行并附着既有AnalysisRolesCapability（避免新模型工具）；调用者不能提供scope或seq。每run单调seq、最多128条，串行化持久写入；**先put成功再emit相同payload**，拒绝额外字段/坏值，所有整数拒绝bool、遵守合同bounds。不能静默丢弃已承诺的持久事件后继续宣称stage成功。source_run_owner/thread验证沿用本run实例与store，别从clientcontext取事件对象。

缺store/失败的稳定行为需明确：必要phase开始无法持久时不能执行下一敏感步骤；查询已执行后阶段持久失败不能伪造success receipt，报告写入/索引顺序不能改变，失败如实返回。CancelledError不吞掉。避免event callback无限等待，沿用run预算或有界短超时，不添加跨服务事件框架。

## 实际阶段与终态

workflow、catalog、sql、authorization、execution、data、writer、reviewer、publish按真实操作前后发送running及终态。authorization包括现有policy/语义授权/EXPLAIN成本门禁；risk从实际计划metadata取固定enum；execution成功/截断的rows/bytes/evidenceIDs从已验证结果取，失败code用合同白名单映射，未知为unavailable，不传自由字符串。

roles的实际AIMessage.usage_metadata若提供合法input/output int可记录为有限观测stats并投影，未知省略，不能拆算RunJournal总量。缓存命中标cached=true，不重复累计已耗tokens；不因事件工作恢复SDK callbacks来采集raw数据。

真实失败/blocked/cancelled与成功分别映射，不把running静默写成succeeded。在worker终态、异常/取消和close前通过可信角色能力的async finish hook收束未完成阶段及workflow；接口只固定status/code，不转发record错误文本。Harness可鸭子类型调用服务端能力，不能import app；保留既有on_run_completed/extension/scheduler回调，不替换它们。已关闭/身份失配不得再emit。

把domain/verified_report.py中固定报告表头calculated_value改为中文“数值”，仅改用户文案，不改冻结DTO字段/算法，也不加字符串替换wrapper。现有英文新增注释在真改动处按AGENTS写中文。

## V2/V3检查

生产安全metadata与runtime事件边界，直接测试contract一致性、未知额外SQL/rows字段拒绝、seq与store游标区分、persist先于emit、live与GET持久payload一致、phase顺序、blocked/失败/取消真实终态、缓存/unknownusage、store失败零敏感后续步骤、关闭拒绝。复用现有受影响tools/reports/worker/Gateway测试，范围定位，不整仓、不构建、不调用模型、不操作真实fixture。

uv --no-config --default-index https://pypi.org/simple --locked --no-sync，不改uv.lock；准确pytest/Ruff/format/diff命令与分批结果。已有数学/SDK/PG证据不无故重跑。完成冻结交主会话审查，之后统一构建与实际SSE/回放验收；不得提前称AS09完成。
