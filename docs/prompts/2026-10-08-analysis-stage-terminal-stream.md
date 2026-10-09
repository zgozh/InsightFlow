# 阶段终态 live 通道独立审查修补

gpt-6-luna/max；只改 stages.py、roles.py、Harness worker.py、直接stage/worker测试和既有后端记录，不改前端/合同/fixture/其他源码。

主会话审查发现实际生命周期缺口：worker先结束并 `_close_agent_stream(stream)`（约1414行），之后finally约1557行才调用roles.finish。Emitter.finish继续使用从Tool内捕获的旧LangGraph StreamWriter；aemit_custom_event只写该writer，RunJournal无通用analysis callback到bridge的映射。因此终态可能只进已结束的graph queue，永久events有但live SSE没有。现有fake writer始终收集，未覆盖closed stream。

最小方案：Emitter.finish先put经过合同验证的terminal records，**不再向旧graph writer发送**，返回已持久化的payload tuple；roles.finish转交；worker在await finish之后、publish_end之前逐项 await bridge.publish(run_id, "custom", payload)。这是可信server capability产出的payload，不引入App import到Harness，不让caller指定run_id/seq；避免重写共享aemit helper或重复put。正常Tool阶段现有persist→aemit保持。未启动任何phase时可返回空tuple；保持finish失败将run转稳定error、取消真实映射、lease ownership guard及close。失败时不能返回未持久化payload。

先写直接worker seam回归：graph stream已经关闭且旧writer不允许再用；finish持久成功后bridge仍收到同scope terminal custom且位于end之前；另测试put失败无虚构success live。V1/V2只跑直接stage/worker受影响节点，保留345已有证据，Ruff/format仅变更文件；不六模块重复、不构建或模型。准确记录复现/结果然后冻结。
