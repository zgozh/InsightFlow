# Phase 6F3F9：默认持久化 run events，验证 Gateway 重启后历史可读

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。先读 `.reviews/phase-06f3f8-post-restart-run-history.md`、`config.example.yaml` 的 `run_events` 小节、`make_run_event_store` 与直接相关的启动/持久化测试。不要重读整个仓库或重跑此前有效的门禁。

## 裁决与目标

InsightFlow 是个人可部署的经营分析工作台，默认交付不应在 Gateway 重启后静默丢失可审计的 run 消息/事件。采用仓库**已有** `run_events.backend=db`，使用默认 SQLite 应用库；不引入 Redis Streams 之外的新服务、独立事件数据库或新适配层。`memory` 保留为显式轻量/临时选项，旧的 memory 事件无法恢复，不能伪造迁移。

当前旧 run `63cfc92a-97d9-446d-ad21-58d71ff97821` 的 events 已随内存 store 消失，报告 artifact 仍在；不得用它当“切换后历史恢复”测试。只验证切换后**新 run** 的重启前后同 ID 读回。

## 实施范围

1. 将 `config.example.yaml` 的默认 `run_events.backend` 改为 `db`，说明与现有应用 SQLite 共享持久化库、memory 重启丢失、旧数据不会补回；按直接受影响的启动/配置契约更新必要的测试与用户配置说明。不要扩大到所有配置项重写。
2. 仅把固定验收 project `insightflow-acceptance-local` 所用的 Git 忽略 `config.yaml` 的该一个非敏感字段改为 `db`；修改前确认精确文件/挂载来源与当前值，保持其余内容、凭据和文件编码不变，不输出配置正文或 diff 中的秘密。若无法安全确认 Gateway 实际使用该文件，停线报告，不猜测。
3. Gateway-only 重启以应用启动期配置；保持同一容器、原三卷、其它四服务与旧 6F1 栈不变。用有界 health/readiness 检查确认 `DbRunEventStore` 真正选中，不接受“配置写了 db、实际 fallback memory”的假通过。不得执行 `down`、删卷、重建业务数据库或重建前端。

## 验证

级别 V2（共享配置/存储契约）+ V3 定点重启集成。先运行受影响的配置解析/`DbRunEventStore` 持久读回或启动装配测试、对应静态/格式检查；不跑后端全套或前端/浏览器套件。若现有测试已充分覆盖，不为机械测试数量新增重复用例；必要时只加一条证明 `config.example.yaml` 默认选择 db 且不会回退 memory 的契约测试。

真实集成只创建**一个**最小、低成本的普通 run（可用当前已配置的 `deepseek-flash`，不要打印 key；无需业务数据库查询或报告发布）。run 完成后只输出安全计数：同 owner 的 run status、messages/events 数量与序号范围。然后仅重启 Gateway 一次，复读**同一** thread/run，要求 status 仍成功、非空消息/事件计数与必要序号一致；不读取/输出消息正文、tool args、SQL、凭据或自由文本。如果已有合成/免模型 run 能通过正式 Gateway 路径形成等价持久事件，可优先用它省费用，但不得直接手工插库替代正式运行链路。若模型/API 或 Gateway 无法完成新 run，明确归类环境阻断，不循环重试。

前述旧 memory run 的空 feed 是既成事实，不能用新配置补救。最小更新 `docs/acceptance/phase-06d-contract-reconciliation.md`、`docs/PROGRESS.md` 和直接相关的部署配置文档：如实记录默认配置、单 run 重启读回证据或阻断；不把 AS-09 全项 SSE/无思维链、AS-12 PostgreSQL 应用库或旧报告数字溯源写成 PASS。

报告放 Git 忽略 `.reviews/phase-06f3f9-durable-run-events.md`，记录变更文件、门禁命令/退出码、原容器/卷保持、是否实际选中 db、重启前后计数、旧 run 不可恢复与剩余风险。生产/config 文档变更独立提交，工作树干净；不 push。遇到明确产品缺陷先给最小证据与修复范围，停在 GPT 复验，不顺手改通用存储架构。
