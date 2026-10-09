# 下一分析角色切片：有限源码取证

完整发布任务继续。metric授权与耐久evidence bridge源码已冻结，另worker仅构建Gateway镜像。你是 `gpt-6-luna` / max，只做下一AS07/08/10切片的有限只读取证，不实施或跑checks。唯一输出 `docs/acceptance/2026-10-08-analysis-role-contract-audit.md`。不得改源码/tests/其余docs/ignored部署脚本，不派Agent、不调用模型、不读真实用户记录。

主会话负责架构裁决，已冻结方向见 ADR0005；你只给实际符号/合同与最小接线候选，不能替主会话引入新目标。用rg --files先找真实文件名，**不要猜不存在的definitions.py**。避免历史文档/整仓扫描。

读取范围：App analytics agent模块实际role definitions(若存在)、reviewer.py受限bare-model调用/绑定/清理接口、tools.py/reports.py/runtime.py现有三工具与耐久collector消费；domain/metric.py与MetricCatalog当前字段；Harness lead_agent/agent.py中Reviewer base-model绑定段，以及现有server-owned reviewer key注入/清洗相关worker行；0005 ADR。

输出最多150行，尽快冻结：

1. 已执行的角色与仅声明的角色分别列真实class/function/line，现行Lead→query→Reviewer→writer到底是哪几次真实model invocation。不要重复已接受bridge/metric验收。
2. 复用现有bounded Reviewer机制实现SQL Analyst/Data Analyst/ReportWriter独立zero-tool有界调用时，哪些最小接线位置/新server-owned capability确有必要，哪些可复用。给字段名/文件所有权候选，不编假代码API。不做通用Agent平台抽象。
3. MetricDefinition目前是否有单位/期间/分母语义字段；AS10确定性数字claim校验在现有evidence列/行/摘要上能证明什么、不能证明什么。提供最小typed contract候选（cell引用/计算/单位期间来源等），指出必要迁移/API变更与消费者，不自行决定扩字段或实现。不能建议“任意markdown数字在任意结果里出现就算正确”。
4. current Reviewer重试/超时/取消/输入输出token budget已实有哪些；新角色事件/SSE可复用的输出钩子是什么（仅定位最相关symbol，不扫整个events系统）。
5. 下一切片最小的生产文件集合与有价值的直接测试名称，分清role/math与后续阶段event/front投影（串行接口freeze）。

若有真正架构疑点按具体矛盾报告，不读更多背景拖延。完成直接报告短结论与输出路径，冻结。主会话会据此写正式实施提示，不直接开始实现。
