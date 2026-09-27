# Phase 6F3F1：复用已发布 run 核对真实轨迹与验收契约

> 执行者：现有 `gpt-6-luna`（max）。先读本文件、`.reviews/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`、`docs/acceptance/acceptance-scenarios.md` 的 AS-07/09/10 与 `docs/acceptance/phase-06d-contract-reconciliation.md` 对应行。不重跑 6F3E10，不启动 5C。

## 目标

6F3E10 已用真实 `deepseek-flash` run `63cfc92a-97d9-446d-ad21-58d71ff97821` 验证：2 条成功 evidence、一次 Reviewer 拒绝、一次 `published`，owner 报告索引/artifact 200、异线程 404。现有验收文档仍写“系统没有 Reviewer 复核”，已与事实矛盾。下一步在**不发新模型请求**的前提下，用这条持久 run 核对后端公开历史/事件与前端轨迹投影的事实范围，修正文档，不把单例成功写成 AS-07/09/10 整项 PASS。

## 一次性切片与验证级别

真实运行历史的只读核对属 V2；文档更正属 V0。若确认同一真实 run 的前端投影存在具体缺陷，才进入最小 V2 修复并做受影响前后端定点测试；不要默认跑全量 pytest、Rstest、Playwright、构建或数据库套件。

1. 核对 HEAD 从 `8bfa30c` 继续、工作区干净、固定 `insightflow-acceptance-local` 仍是原 5 容器/3 卷/1 网络。只复用已有 DPAPI admin、HTTP helper 和已发布 run；不创建新的用户、线程、报告、模型请求或数据库写入。若固定栈不可用，先只做最小环境诊断；无需再次重建整个栈。
2. 从服务端公开的同 run messages/page、run events 与报告索引只读接口取得信息，在进程内投影/计数，**不保存或打印原始响应、模型文本、SQL、结果行、tool args、token、凭据或 artifact 正文**。记录固定工具名与调用/结果计数、安全 code、evidence ID 是否为摘要形状、Reviewer approved/rejected/limited 等状态是否可推导、artifact 引用是否 owner-scoped。AS-13 只检查平台结构化字段；任意用户/模型文本与 artifact 正文不在“绝无敏感内容”保证内。不要把 Reviewer 的内部 `category` 日志当成公开轨迹字段。
3. 对照 `frontend/src/core/analytics/trace.ts` 与 `analytics-trace-panel.tsx` 的现有纯投影契约。可用已有前端单测或一次登录后的只读页面观察证明真实 run 的轨迹卡片；若无法安全驱动浏览器，给出从公开 API 形状到纯函数的可复核中间证据并诚实标注“未做真实浏览器闭环”。不要为一次观察新建第二状态源、SSE 通道或持久 trace 表。若发现具体映射缺口，仅修该缺口和直接回归；不要借机重新设计聊天 UI。
4. 更新 `docs/acceptance/acceptance-scenarios.md` 中 AS-10 的陈旧现状说明，以及 `docs/acceptance/phase-06d-contract-reconciliation.md` 的 AS-07/08/09/10 对应证据/限制；`docs/PROGRESS.md` 追加 6F3E10 与本切片证据。必须区分“真实单例报告发布/Reviewer 有限流程门已通过”和“任意数字数学证明、多专职 Agent、全量 SSE 轨迹、跨主体隔离、计划任务”等尚未验收内容。AS-10 不能因一个 Markdown 报告而宣称完整 PASS；AS-07 的目标多角色链仍未实现，不偷偷改目标契约。
5. 若只改文档/忽略的验收 helper，V0：readback、精确 diff、`git diff --check` 即可；不跑应用测试。若有生产/前端代码修复，按受影响面跑最小定点测试、类型/格式检查，必要时用同一持久 run 做只读回归，**不发新模型 run**。

## 交付

写脱敏报告 `.reviews/phase-06f3f1-real-trace-readback-and-contract-reconciliation.md`，列实际 HTTP 状态、固定计数/状态、可见与不可见的轨迹字段、被修正的文档结论、未验证项。文档更新一个独立提交；若发现代码缺陷则与其直接测试另作一个独立提交。保留验收栈与 DPAPI，不触碰旧 6F1 项目和历史残留目录。完成后停在 GPT 复验，不自行启动下一切片。
