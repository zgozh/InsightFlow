# Phase 6F3D1：单次真实 run 未证实报告发布的只读根因审计

你是 InsightFlow 的只读调查员。先读 `.reviews/phase-06f3c3-isolated-reviewer-live-rehearsal.md` 与直接相关的受控分析入口、Lead 提示/skill、Reviewer、writer、报告索引及结构化轨迹代码。不要重读整仓历史。6F3C3 已完成一次真实登录、受限 datasource/policy 与唯一 Gateway analysis run（stream 200、run success），但没有保留足以确认 Reviewer/writer/report 的安全结构化证据；这**不是**“报告必然不存在”或“Reviewer 必然失败”。临时 Compose 项目及其卷已清；遗留 `.reviews/phase-06f3c3-home-r26a9c2e` 等待用户手动删除，**本任务不得打开、移动、修改或删除它**。

## 调查目标

1. 沿“分析 Lead 收到请求 → 工具可见与选择 → query evidence → Reviewer 调用门禁 → writer → report index → artifact GET/前端轨迹”逐边界列出：代码中的触发条件、可从现有 6F3C3 报告证实的事实、尚缺哪一项安全元数据。区分确定性产品缺陷、模型可能未选工具、测试观测不足；没有证据不得推断根因。
2. 对照 6F1 曾成功发布报告的路径和 6F3C3 唯一 run 的变化（Reviewer、工具限制、模型字段修复、数据源/策略、提示词、环境），只比较直接相关的差异。不得因 run status=success 就推断 report published，也不得把 report_published=false 摘要等同报告表为空。
3. 判断能否**完全不再调用模型、无需用户会话、不接触待清理 home**，从仍保留的安全结构化日志或已记录报告中确定 Reviewer/writer 是否执行；若不能，明确最小的下一次彩排观测方案（例如在 run 结束前记录既有稳定 tool code/receipt 或只读报告索引），不先造通用 tracing/遥测系统。
4. 输出一条最小可检验假设与下一步建议：若有代码缺陷，指出精确入口、复现条件及 V1/V2 定点验证；若只是观测不足，给出下一次单 run 的 V3 证据采集契约；若已有安全失败码，准确解释它。不要擅自修代码、改配置、创建数据、启动 Docker、发模型请求或跑全量套件。

## 交付

只读/V0：文件与相关契约回读、必要的静态调用链检查。报告写入 Git 忽略的 `.reviews/phase-06f3d1-report-chain-root-cause-audit.md`，使用“已证实 / 未证实 / 假设”分栏，记录精确文件/符号与最小下一步；不含原始 SQL、结果行、模型文本、凭据、token、DSN 或报告正文。无生产提交。完成后向主会话交简短结论并停在此审查门禁，由 GPT 制定后续实施提示词。不得把遗留临时账号目录的清理状态改写为已完成。
