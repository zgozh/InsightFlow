# Phase 6F3E9：工具可见性预检与一次明确报告请求

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e8-writer-noninvocation-audit.md` 与 `.reviews/phase-06f3e7-fix-02-existing-admin-role-contract.md`。只复用当前 `insightflow-acceptance-local`、已有管理员 DPAPI 和合成策略；不重建容器或重配业务数据。

## 目标

上一 run 有成功 evidence，但用户请求写成“若证据足够则留存”，最终 AI 未调用 writer。要先分清工具是否可见，再用**最多一次**无歧义的报告请求验证完整链路。不能把一次模型不调用直接归因于模型能力，也不能把单条 evidence 自动当作足够证据。

## A. 不发模型的可见性门禁（V1）

1. 在现存 Gateway 镜像/当前有效配置下，只读取 `authorization.enabled` 布尔值和 `get_available_tools(analysis_mode=True)` 的三个固定工具名布尔可见性。若 authz disabled，`apply_tool_authorization` 按现有代码为 no-op；若 enabled，用本管理员受信 context 执行相同过滤，仅输出过滤后三个名字的布尔值。不得打印配置值、主体 ID、权限列表、工具参数或模型信息；不启动第二个 Gateway。
2. 只要不能证明 writer 进入**当前有效配置的授权后工具集合**，就在此停止，不发 run；报告具体阻断步骤。预检不要扩成新的通用工具框架，10 分钟内不能完成则停线。

## B. 最多一次真实 run（V3 定点）

3. 若三工具均可见，复用现有管理员与 CSRF、合成 datasource/schema/policy，创建新的 `kind=analysis` thread。明确请求：“请只基于本次实际成功的受控查询证据写并**留存**一份简短 Markdown 报告；先查询 `demo.orders` 中获准的 `region` 与 `amount` 的分组金额，若只能证明有限事实，就在报告中明确限制和证据不足，不编造其他结论；需要调用 `write_analysis_report`，未得到发布回执不能称已保存。”不得给模型提供真实 SQL、凭据或额外权限。若没有任何成功 evidence，应如实失败，不强迫绕过 writer 门禁。
4. 只发送一次 run；用 `Content-Location` 确认 run ID，完整消费 stream 后从现成 run-messages API 提取本 run 的工具名/稳定码与 evidence 数量。绝不保存模型正文、SQL、结果行或 tool 参数。writer 若调用，读其稳定码；若 `analysis_review_unavailable`，只取 Gateway 同 run 固定 Reviewer stage。若 published/existing，检查 owner 报告索引本 run 数量与 owner artifact/异线程或异主体访问状态码；不得读出正文。若 writer 仍为 0，分类最终回复但不输出文本，不再发第二 run。

## 资源与交付

- 现有固定验收栈、DPAPI 凭据和旧 6F1 项目均保留；不轮换账号、不 `down --volumes`。允许新建本次 thread/run，除此不做额外测试数据变更。旧 6F1 当前容器为 exited，**不要恢复或清理**。
- 不改生产代码、提示词、配置、依赖或永久测试；不跑全量 pytest、构建或 E2E。报告写 `.reviews/phase-06f3e9-explicit-report-on-existing-stack.md`，仅安全状态/布尔/计数/稳定码/固定 stage；若发现缺陷，报告最小复现，不自行修复。`.reviews/` 不提交；完成停在主会话复验。
