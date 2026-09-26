# Phase 6F3E1：真实 Gateway run 的 Reviewer unavailable 根因定位

你是 InsightFlow 的只读调查员。先读 `.reviews/phase-06f3d2-instrumented-report-live-rehearsal.md`、`backend/app/analytics/agent/reviewer.py`、`backend/app/analytics/agent/reports.py` 与直接相关的 Gateway/Lead runtime 绑定代码。6F3D2 的唯一真实 run 已证实 query `executed` 且 evidence 存在、writer 被调用并返回 `analysis_review_unavailable`；run status success **不**等于报告发布。Reviewer 单独直连 `deepseek-flash` 曾 HTTP 200/approved，但不能替代 Gateway run 内绑定与输入。临时 6F3D2 Compose 项目及 app-home 卷已清零；旧 6F1 项目不动。不得访问待用户手动删除的 `.reviews/phase-06f3c3-home-r26a9c2e`。

## 定点调查

1. 从 writer 产生 `analysis_review_unavailable` 的每一个实际分支往回追：run-owned Reviewer 是否注入/匹配、Lead base model 是否成功绑定、输入快照与大小限制、`ainvoke` 异常/超时、实际请求字段、严格 JSON 解析、外层异常捕获。列出能被现有安全证据排除的分支、仍无法排除的分支及所需的最小证据。不要凭一次直接模型成功推断 Gateway 调用成功。
2. 比较当前 Gateway `run_context` → worker runtime context → Lead `create_chat_model`/`bind_lead_model` → tool runtime 的真实对象/ID 数据流。优先使用已有直接相关测试；如静态检查不能确定某个绑定分支，可运行**一个最小本地假模型/假 runtime 定点复现**（不改生产文件、不触发真实 Provider/Docker），只输出布尔与稳定码。不要跑全量套件或为理论分支新增一批永久测试。
3. 只形成一个可证伪的首要假设与下次最便宜的验证方案。若已能确证代码缺陷，给出精确函数/条件和最小修复边界；若仍缺运行时证据，设计一次只投影内部安全类别（例如 `binding_missing`、`provider_error`、`timeout`、`invalid_json`）的短期受控探针，**不得泄露**异常文本、原始 prompt/response、SQL、结果行、凭据或报告正文，也不得在本任务实施该探针或发真实模型请求。

## 交付

V1/V2 定点调查（无代码变更时仅静态 readback；如运行假模型，只记录命令和退出码）。报告写 Git 忽略的 `.reviews/phase-06f3e1-reviewer-unavailable-root-cause.md`，按“已证实 / 未证实 / 假设 / 下一最小动作”组织，注明文件与符号。无实现提交，不改私有配置、不启动 Docker、不清理任何目录。交回 GPT 审查后停此切片，由 GPT 决定修复提示词。
