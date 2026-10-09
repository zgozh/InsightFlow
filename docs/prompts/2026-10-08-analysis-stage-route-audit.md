# AS09 阶段事件接线有限取证

gpt-6-luna/max，只读取证。唯一输出 `docs/acceptance/2026-10-08-analysis-stage-route-audit.md`，最多45行；不改源码、不跑测试、不操作容器/真实记录。另一worker正改角色集成，请不要读它尚未冻结的新实现做结论。

只定位既有 custom_events.aemit_custom_event、Gateway worker/journal/live SSE/replay路由与frontend实际thread流消费入口（按rg定位）。列出确切现有函数/类型/文件行号、server消息custom命名与客户端onCustom处理格式、live与持久replay是否走同一通道、Frontend现有可复用阶段显示组件/状态、注册新analysis_stage的最小owner文件集。

给一个可评审的有限契约候选：版本/run_id/seq、SQL/Data/Writer/Reviewer/authorization/execution/publish等闭合stage/status，只有safe counts/risk/duration/code/evidence IDs，绝无SQL/结果行/secret/plan token/CoT。实际token usage来源若没接口须标unknown，不能捏造。指出序号/duplicate/replay处理与取消/失败的现有落点。不设计通用事件框架、不开放新工具、不写不存在的实现或AS09完成结论。

主会话据事实冻结下一阶段协议和前后端接线；返回短报告并冻结即可。
