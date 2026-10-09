# Bridge 独立审查后的文档收口

主会话已独立读完evidence_bridge、固定file能力、query/report/Gateway diff与直接测试，没有发现新的执行/恢复权限缺陷。两个Windows symlink跳过保留到Linux里程碑，不假称通过。源码接线边界已接受，本切片只改非执行文字。

由 `gpt-6-luna` / max 立即做三处V0收口，不读历史背景、不跑应用测试：

1. `backend/app/gateway/services.py::_analysis_services_available` 本轮改写的英文docstring用中文说明启动bundle/绑定identity/耐久repo门禁。
2. `backend/app/analytics/agent/tools.py` 本轮新增“Run-owned capabilities never turn an ordinary chat...”注释改中文，说明为什么collector不把普通聊天变成analysis。
3. `docs/acceptance/2026-10-08-durable-evidence-gateway-bridge.md` 标题中文化，补自己确实执行的首轮pytest与两次定点复验、Ruff的精确命令和结果。命令从你的实际调用记录取，不猜，不把重叠测试计数相加。记录主会话源码审查已接受，但未部署/角色数字核验等未完成。

只改上述三个文件的文字，不改任何生产语义、test、其他AGENTS/PROGRESS或前端。V0 readback/git diff --check足够；纯docstring格式若有需要仅受影响Python Ruff格式检查，不跑新Ruff whole-repo或pytest。立即冻结给主会话，不扩展工作。
