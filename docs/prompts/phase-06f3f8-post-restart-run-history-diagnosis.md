# Phase 6F3F8：Gateway 重启后旧 run 消息/事件变空的定点诊断

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。6F3F7 `d3acbb2` 的文档事实已接受；本切片**只诊断，不实现修复**。先读 `.reviews/phase-06f3f7-existing-report-provenance.md` 与 6F3F1 同 run 非空回读证据，再查直接相关代码。

## 问题边界

同一已完成 run `63cfc92a-97d9-446d-ad21-58d71ff97821` 曾由既有脱敏 reader 读到 catalog/query/writer `1/6/2`、24 events；固定验收栈的 Gateway 后来退出并在 6F3F5 原容器内重新启动。6F3F7 用**同一个 reader** 读取该 run，status 仍为 success，但 messages/events 都是 HTTP 200 的空集。与此同时，报告索引、artifact 与前端分析 trace 仍可读。需要确定这些数据分别来自何处、空集是设计上的非持久数据过期，还是读取/恢复缺陷；不能凭表面 200 推断全链路持久化正常。

## 定点调查

按 `systematic-debugging` 的证据顺序，优先对照一次旧/新 reader 的 endpoint、thread/run ID 与 pagination 参数；若一致，沿 `backend/app/gateway/routers/thread_runs.py` 的 messages/events 处理、run journal/store 写入与启动恢复、前端 trace 的数据来源做最短调用链追踪。必要时只读检查固定 Gateway 的持久化配置、相关表/键的**结构和计数**，以及原容器的重启时间；不读取、输出或保存消息正文、原始 SQL、结果行、报告正文、token、密钥或 cookie。不修改数据库/Redis/卷，不停止或重启任何服务。

必须明确回答：

1. 6F3F1 与 6F3F7 是否真正调用同一历史 API/参数？若不是，给出差异并用**一次**更正后的安全计数读回验证。
2. 若 API 一致，messages/events 的权威来源是持久库、Redis 还是 Gateway 进程内存？重启后空集是否由现有代码/配置确定地产生？前端已看到的 trace 又从哪条数据路径来？
3. 这是符合已公开契约的寿命限制，还是产品缺陷？如果是缺陷，指出最小修复边界与一条有价值的回归测试建议，但本切片不改产品代码。
4. 当前证据是否足以恢复 6F3F7 的数字溯源？若仍不行，保持 `ambiguous`，不要为了取得报告数字重发 Agent run。

验证级别是只读诊断 V1：源码/配置调用链、既有两份安全计数证据，必要时一次同 run 的精确只读计数。不要重跑全套测试、Docker build、浏览器、模型或新的业务查询；不要扫描整库。若不能在直接相关路径内确定根因，列出剩余两三个可证伪假设与下一项最便宜检查后停线。

脱敏报告放 `.reviews/phase-06f3f8-post-restart-run-history.md`；仅记录路径、结构性事实、状态/计数、可信度与建议，不附数据正文。若证实已发布文档对持久化作了错误承诺，可在同一切片最小修订该句并做 V0 readback/diff check、独立提交；否则不做空提交。完成后停在 GPT 架构复验。
