# Phase 6F3E9 Fix 01：已证明工具可见后执行一次明确报告 run

> 执行者：`gpt-6-luna`（max）。继续 `docs/prompts/phase-06f3e9-explicit-report-on-existing-stack.md` 的 B 段；A 段由主会话只读复验闭合，不再重复工具探针。先读 `.reviews/phase-06f3e9-explicit-report-on-existing-stack.md` 与本文件。

## A 段裁决与证据

同一固定 Gateway 容器里，系统 `python` 导入 `deerflow` 失败（`ModuleNotFoundError`，exit 1）；生产镜像应使用仓库规定的 `uv run --no-sync python`。主会话已用后一解释器、`-w /app/backend`、不联网不调用模型执行两个只读探针，均 exit 0：当前有效 `authorization.enabled=false`；`get_available_tools(analysis_mode=True, app_config=get_app_config())` 对 `inspect_business_catalog`、`query_business_data`、`write_analysis_report` 三个固定名字均返回 true。现有 `apply_tool_authorization` 在该布尔值为 false 时是 no-op，Lead 分析模式直接把配置工具传给 `create_agent`。因此当前固定栈的授权后 writer 可见性门禁已通过。不能把此证据扩大成“历史 run 的工具 schema 已被持久记录”。

## 唯一实施切片（V3 单场景）

1. 只复用 `insightflow-acceptance-local` 既有容器、命名卷、DPAPI 管理员和合成 datasource/schema/policy。旧 6F1 项目不启动、不清理；当前验收栈已运行，不 `compose up/build/recreate`。确认已登录的 admin、CSRF 和现有策略可用，失败就停，不为了准备反复修改测试数据。
2. 新建一个 `kind=analysis` thread；将被忽略的验收 runner 中**仅用户请求文本**改成无歧义版本：明确要按 `region` 汇总获准的 `amount`，只引用本次成功查询的 evidence，必须尝试 `write_analysis_report` 留存 Markdown；若证据有限就在报告中写局限，不推断其它字段；若没有任何成功 evidence 则如实不发布。不要把原始 SQL、凭据或模型秘密塞进请求。其余 runner 逻辑沿用已验证版本。
3. 最多一次真实 `deepseek-flash` Gateway run。用 `Content-Location` 取 run ID，消费 stream 后调用同 run messages API；只记录三工具调用计数、稳定 code 与成功 evidence 数，不记录 SQL/结果行/模型正文/tool 参数。若 writer 返回 `analysis_review_unavailable`，取同 run Gateway 固定 Reviewer stage；若 published/existing，查 owner 报告索引与 owner artifact/异线程或异主体访问的 HTTP 状态，不读取正文。writer 仍未调用则分类最终答复，但不重试模型。

## 交付与停止

报告写 `.reviews/phase-06f3e9-fix-01-explicit-report-run.md`，含主会话 A 段证据、一次 run 的安全状态/计数/Reviewer stage、报告及 artifact 状态、验收栈资源。不得修改生产代码、配置模板、lockfile或永久测试；不跑全量测试、构建、Playwright。保留固定验收栈和 DPAPI，`.reviews` 不提交；发现缺陷只报告最小复现，停在主会话复验。
