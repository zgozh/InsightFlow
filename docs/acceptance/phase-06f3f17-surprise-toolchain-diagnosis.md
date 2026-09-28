# Phase 6F3F17：小惊喜工具链诊断

状态：完成定点诊断与固定验收实例配置修复，待 GPT 独立复验。

## 结论

6F3F16 的模型没有调用工具，不能归因为模型不遵循要求：当时固定验收实例的有效普通聊天工具集没有 `write_file`，而请求明确要求写 HTML。真实 Lead 装配路径会把 `AppConfig.tools` 与内置工具组合后传给 `create_agent`；`write_file` 不是内置工具，需由运行配置显式启用。公开 `config.example.yaml` 已有该工具配置，因此没有发现生产代码装配缺陷。

只在 Git 忽略的固定验收配置 `.analytics-demo/config.yaml` 中加入 `write_file`，并保留原始字节备份 `.analytics-demo/config.yaml.phase-06f3f17.bak`（均为 ignored；备份哈希与修改前配置哈希相同）。配置由只读挂载提供给 Gateway；未读取或输出配置全文、凭据或业务值。Gateway 观察到配置变化并完成热加载，认证后的 `/api/models` 返回 200 且包含精确模型 `deepseek-flash`。没有重启或重建任何容器。

## 上游与当前“小惊喜”路径

- 上游 `upstream-v2.1.0-rc0` 的 `frontend/src/components/workspace/input-box.tsx` 使用 `ConfettiButton`；`en-US.ts` 的标签/输入为 “Surprise” / “Surprise me”，`zh-CN.ts` 为“小惊喜” / “给我一个小惊喜吧”。点击只把文本放入输入框并聚焦，不自动提交；随后仍走普通聊天提交。
- 上游还含 `skills/public/surprise-me/SKILL.md`：它会发现并组合可用技能，缺少其他技能时可回退到交互式 HTML，并要求呈现产物。该技能在当前树已删除（`51f2bee`）。因此当前实现保留的是简化的提示词示例，不是原上游的技能编排闭环。
- 当前 `frontend/src/components/workspace/input-box.tsx` 的 `SuggestionList` 展示普通建议卡；中英文案分别为 “Make a little surprise” 和“创建一个小惊喜”。提示要求围绕 `[theme]` 生成可在沙箱预览的自包含交互 HTML；选择后只是填入输入框并选中占位符，用户填写主题后再走普通聊天提交。当前代码路径没有专用 `mode=skill`，也不会因点击示例自动发送。
- UI 的真实发送在 `frontend/src/core/threads/hooks.ts` 中走 `thread.submit`，输入消息由 `buildThreadSubmitMessages` 组装，run context 由 `buildRunContext` 从当前设置构造，SDK 配置带 `threadId`、`streamResumable` 及 UI 原有 `recursion_limit=1000`。本轮直连 runner 则显式指定 `assistant_id=lead_agent`、`model_name=deepseek-flash`、`thinking_enabled=false`、`is_plan_mode=false`、`subagent_enabled=false` 和合成工具要求；因此只用于 API/工具诊断，不代表 UI 的全部请求字段或点击时序。6F3F14 的即时计数夹具不能证明 UI 未发送。

## 工具装配与配置证据

相关实现位于 `backend/packages/harness/deerflow/tools/tools.py`、`backend/packages/harness/deerflow/agents/lead_agent/agent.py` 和 `backend/packages/harness/deerflow/sandbox/tools.py`：普通 Lead 调用 `get_available_tools`，配置工具经 resolver 加载，`write_file` 与内置 `present_files` 最终传入 `create_agent`。固定实例使用 `deepseek-flash` / `ChatOpenAI`，`bind_tools` 可用；沙箱为 `LocalSandboxProvider`，host bash 未开放，tool search 关闭。

修复前有效工具名（排除 MCP）为 `ask_clarification`、`inspect_business_catalog`、`list_uploaded_files`、`present_files`、`query_business_data`；缺少 `write_file`。有效配置仅启用了两个 analytics 配置工具及较窄的业务工具集合。模板 `config.example.yaml` 的 `tools` 列表中已有 `write_file`，位置在 `config.example.yaml` 的工具配置段。最小修复只添加这一项，未放宽工具组授权、沙箱策略或 host 命令能力。修复后 Gateway 运行时解析出的工具集含 `write_file` 与 `present_files`。

该实例的 `authorization.enabled` 为 false，普通聊天请求未指定自定义 agent/tool-group 限制；`tool_search` 关闭。故未发现额外授权过滤或延迟工具发现导致 `write_file` 不可见。

## 唯一新 run 与 artifact 读回

修复和 Gateway 热加载证据成立后，本切片仅发起一次新的模型 run；旧 run 未重放。登录、管理员身份、模型清单、thread 创建和 stream 均为 HTTP 200。模型名精确为 `deepseek-flash`。

- thread：`6ce643e7-761c-4ba2-b110-97fdb8e380fa`
- run：`a7b51a20-0c59-4eff-9adf-c64bdb256d61`
- stream：HTTP 200，收到 `end`，未超时；同 run 状态 API 为 `success`。
- 本报告中的“一次”指一个 Gateway run；未单独记录底层 Provider API 请求总数。
- 持久 messages：6 条，含 1 条 human、3 条 AI response、2 条 tool result；AI 工具调用计数为 `write_file:1`、`present_files:1`。messages 投影的关联结果只计到 `write_file:1`，未将结果关联到 `present_files`。
- 同 run events：HTTP 200，共 11 条；可见 1 次 `write_file` 调用与 1 次 `present_files` 调用，结构化工具结果投影含二者。该投影对 `write_file` 的结果计数为 2，与 messages 投影的 1 不一致，故不声称两种投影的逐条结果关联完全一致。
- 预期虚拟路径 `/mnt/user-data/outputs/star-surprise.html` 出现在同 run 工具轨迹中。以该 thread 的 owner-check artifact 路由读取元数据，HTTP 200、`text/html`、attachment；未读取响应正文。由此证明此 run 产生并提交了预期类型的 owner-scoped artifact，但不证明浏览器预览 UI 已展示它。

此前 6F3F16 同 run 的安全进程内分类为：AI 回答输出了代码并明确表示缺少工具，没有证据声称文件已写成；其持久消息仍是零工具调用。这与当时有效工具清单缺少 `write_file` 一致。原回答正文未输出或写入报告。

## 验证范围与边界

这是运行配置边界的 V2 定点验证：只读核对运行时工具解析/Lead 装配、配置热加载日志、认证模型清单，以及一条完整等待的真实 Gateway run 和同 owner artifact 元数据 GET。没有改生产代码、重建/重启服务、运行全套测试或 Playwright，也没有第二次模型请求。固定 `insightflow-acceptance-local` 的 5 个容器、3 个命名卷及数据均保留。

已证实：固定验收配置缺少 `write_file` 是 6F3F16 没有工具调用的首个可证原因；补入后模型调用 `write_file` 与 `present_files`，run 成功且 owner artifact 路由可读。

未证实：真实浏览器从“小惊喜”卡片到同类产物的完整交互；消息与事件投影中 `present_files` / `write_file` 工具结果的逐条关联一致性；当前简化提示词是否等同上游 `surprise-me` 技能的惊喜质量。若要验收 UI 链，下一步应在同一固定栈做一次带异步等待的浏览器试验，分别确认输入填充、显式提交、stream/run 建立、同 thread artifact 状态及预览；不应把此 API run 外推为该浏览器验收。
