# Phase 6F3F16：直连接口 Agent→HTML artifact 单次试验

日期：2026-09-28。结果：**Gateway chat run 成功；Agent 未调用工具，未生成或交付 HTML artifact。** 不将 API run 成功表述为 artifact 闭环，也不将这条直连 API 路径表述为聊天 UI 提交成功。

## 固定环境与认证

- 起点 `e7339a0`，初始工作树只有本提示词未跟踪。使用固定 `insightflow-acceptance-local`，入口 `http://127.0.0.1:29384`。操作前为五个原容器；Gateway、PostgreSQL、Redis healthy，Frontend 与 Nginx running；项目有三个原命名卷。本轮未运行 Compose 状态变更命令、未重建或删除容器/卷。
- 复用既有 DPAPI 保护的验收管理员凭据，在 PowerShell/Python 进程内解密并登录；登录 HTTP `200`、`/api/v1/auth/me` HTTP `200` 且 `system_role=admin`。凭据、Cookie、CSRF 值均未输出或写入试验文件。
- 认证后 `/api/models` HTTP `200`，仅在内存核对到精确模型名 `deepseek-flash`；未读取或记录 provider 密钥、base URL 或配置内容。

## 一次真实 Gateway run

- 按工作台普通聊天契约创建新线程：`POST /api/threads`，只发送新 UUID，HTTP `200`；返回 thread ID 与请求匹配，`analysis_mode` marker 未设置。没有创建 analysis thread，也没有重放 6F3F14 的用户提交。
- 以 `POST /api/langgraph/threads/{thread_id}/runs/stream` 发起唯一一次 run。请求结构对照前端 `createThread`、`thread.submit` 与已安装 LangGraph SDK：`assistant_id=lead_agent`、一个普通 human 消息、`context.model_name=deepseek-flash`、聊天默认 `recursion_limit=1000`、`stream_mode=[messages-tuple, updates, custom]`。合成主题为星空，要求生成单文件交互 HTML、写入 `/mnt/user-data/outputs/star-surprise.html` 并调用 `present_files`；未添加其他业务数据或权限。
- Run stream HTTP `200`，`Content-Location` 为 `/api/threads/557a2913-fe28-483b-b8f2-d6c89dc2348f/runs/17720962-ff57-4bdd-ad9e-95e4906567cf`，thread 与 run 关联一致。流中观察到 `messages=4313`、`metadata=1`、`updates=7`、`gap=1`，随后连接关闭且未观察到 SSE `end`。这 4313 是 SSE 消息帧，不是模型请求数；没有把流关闭误判为 run 完成。
- 同一 owner 随后只读查询 run 资源，HTTP `200`、最终状态 `success`。该 run 的持久事件 HTTP `200`、共 5 条：`run.start=1`、`llm.human.input=1`、`llm.ai.response=1`、`run.delivery=1`、`run.end=1`。Run messages API HTTP `200`、2 条：1 条 human input、1 条 AI response。结构化读取未见任何 AI tool call 或 ToolMessage/result；没有 `write_file`、`present_files` 调用，也没有稳定工具状态码或 artifact 虚拟路径。未读取或输出 AI 正文、HTML、工具参数或其他自由文本。
- 对本次请求的预期 artifact 虚拟路径，通过同一 owner 的受权 artifact API 做只读 GET：HTTP `404`，未读取响应正文。因此没有产物可交付，也没有执行浏览器预览或点击验证。唯一试用 thread 保留在固定验收栈中；没有 artifact。

## 结论与边界

| 子链 | 证据与结论 |
| --- | --- |
| 认证与 API run | **已验证**：管理员认证、精确模型名可用、新普通 chat thread 创建、唯一 Gateway stream HTTP 200，最终 run `success`；持久日志有 1 条 AI response。 |
| 模型→工具→文件/交付 | **未闭环**：持久 AI response 无 tool calls；工具结果为 0；预期路径 owner GET 为 404。最早可证断点是 AI 响应后未产生工具调用。本轮未检查模型正文来推测原因，也未确认是产品缺陷。 |
| 聊天 UI 提交与 artifact 预览 | **未验证**：run 来自认证直连接口，不是浏览器聊天提交；没有 HTML artifact，所以没有浏览器预览/交互证据。 |

没有重发模型请求、取消 run、修改产品代码或更新服务。真实 Provider 请求总数未从供应商账单/遥测核实；本轮只有一个 Gateway run 请求，持久事件记录 1 条 LLM response，未触发第二个 run。后续若继续，应先决定是否接受一次新的有界试验或改用 UI 链路；不应把本次无工具调用的结果包装成 artifact 成功。
