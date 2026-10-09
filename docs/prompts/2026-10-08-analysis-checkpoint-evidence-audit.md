# checkpoint 续跑证据绑定定点审查

实施者：gpt-6-luna / max。本切片只读生产源码，只写本切片审查记录 `docs/acceptance/2026-10-08-analysis-checkpoint-evidence-audit.md`，不修改其他文件、不构建、不启动容器、不调用模型。

用户要求 AS-01～AS-15 完整发布，PostgreSQL 必验、MySQL 可选。角色链、数值验证、耐久 evidence、阶段流已完成；最新终态修补已独立审查。Frontend 镜像已成功。Gateway 构建前需确认 ADR0005 的续跑证据承诺，不能先承诺全部恢复。

阅读相关模块 AGENTS，以及 `docs/decisions/0005-controlled-analysis-evidence-and-roles.md`、Gateway services 的 checkpoint 选择/校验与分析 collector 发行、analytics agent evidence_bridge 与仓储接口、Harness checkpoint 的 run provenance。仅追踪相关符号，不读全部历史记录或整套测试。

问题：新的 run 从服务器验证的同 owner/thread checkpoint 继续时，如何解析 checkpoint 工具历史引用的原 run 成功 evidence？当前 collector 若仅绑定新 run，是否必然拒绝？区分：普通新提问重新查询，与显式 checkpoint 续跑。只报告代码可证明的事实。

若确有缺口，给出最小可实施方案：服务器依据可信 checkpoint metadata / durable run 关联获取来源；客户端 source_run 字段不可信；同 owner/thread、真实 checkpoint 来源与 evidence/artifact 完整性必须校验；不能跨用户/线程或任意 run 复用。明确涉及文件与可复用函数、来源关系不存在时 fail closed 的行为、3～5 个有价值回归边界和预计 V2 检查。不要增建恢复框架/服务，不改变表结构除非确实必要。

若现有路径已覆盖，给出关键代码行与一个最小直接验证命令，不能只以旧 acceptance 自报通过代替源码事实。尽快冻结交回主会话作架构裁决。
