# Phase 6F3B2：安全 Reviewer 回执与分析轨迹投影

你是 InsightFlow 实施者。基线为 6F3B1 `42fdec8`。本轮只让**现有分析 SSE/历史消息**安全呈现 Reviewer 门禁，不新增第二套状态源、run-event 类型、数据库表或前端路由；不声称 AS-09 全部完成。先核对 `backend/packages/harness/deerflow/runtime/serialization.py` 对 `write_analysis_report` ToolMessage 的投影和 `frontend/src/core/analytics/trace.ts` 的现行工具映射。

已知差距：6F3B1 的报告工具会返回 `analysis_review_rejected` 等稳定码，但现有 `_SAFE_ANALYSIS_REPORT_CODES` 没收录它们，外发/历史投影会折叠成 `analysis_report_result_unavailable`；前端轨迹仍识别旧 `publish_analysis_report`，不识别当前唯一的 `write_analysis_report`。因此用户看不到可信的 Reviewer 结果。不要直接把未经白名单处理的 ToolMessage 原文传给 UI。

## 单一相干切片

1. 在分析报告 ToolMessage 的**唯一安全投影**中加入本次实际会产生的稳定 evidence/Reviewer 失败码；只有 `analysis_review_rejected` 才允许有限枚举的 `reason_code`，其他新增字段、自由文本、Markdown、SQL、rows、token、异常文本一律丢弃。成功回执继续只携带既有安全 report ID、artifact path、evidence IDs。SSE、持久历史与 API 读取沿用这一投影，不改普通工具。用合成敏感哨兵检查所有入口。
2. 前端轨迹识别当前 `write_analysis_report`。由**投影后的安全回执**派生 Reviewer 阶段：`published`/`existing` 才能显示“复核通过”；`analysis_review_rejected` 显示拒绝及有限 reason；`analysis_review_unavailable`、输入超限、尝试耗尽只显示失败/受限，不推断其有通过结论。evidence 预检失败、损坏回执和未知码不能伪装成 Reviewer 通过；发布失败但无独立 Reviewer 状态时不得臆造审核结果。报告 artifact 只在真正成功且路径满足现有规则时显示。不要从 `args.markdown`、ToolMessage 自由文本或隐藏的思维链构造轨迹。
3. 维持轨迹面板的现有布局与移动端行为，新增中文/英文简短 Reviewer 标签和必要的稳定 reason 文案；不额外设计大页面。审查旧 `publish_analysis_report`、`task` 等映射是否仍用于普通聊天历史，不能为了扫描归零机械删除。更新直接相关的代码注释/模块指南；AS-07/08/09/10 状态保持未整体验收。

## 比例验证与交付

这是 V2 共享序列化/前端契约，带 AS-13 安全投影要求。做一个关键负例先 RED：投影前 Reviewer 稳定码丢失或敏感哨兵会外泄；随后实现并运行受影响的 backend serialization/事件读取测试、frontend trace 纯函数/DOM 测试、前端类型检查与改动文件格式检查。只有这些证据不足时才扩大；不跑全量后端、全量 Playwright、Docker、真实数据库或模型。检查 `git diff --check`，记录具体命令与退出码，保持固定上游 tag 和锁文件不变。

单独提交本切片，在 `.reviews/phase-06f3b2-reviewer-trace-report.md` 报告文件清单、证据、未覆盖的 AS-09 条款与剩余风险，工作树干净后停 GPT 复验；不启动下一阶段。若发现现有 SSE 消息根本无法在不改变事件协议下安全呈现 Reviewer，先报告真实调用链和最小协议改动，不自行扩权。
