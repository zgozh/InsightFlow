# Phase 6F3F19：既有产物到聊天 UI 的投影闭环

状态：已修复并以既有 run 完成零模型浏览器复验，待 GPT 独立复验。

## 根因与修复

同 owner 对既有 thread `6ce643e7-761c-4ba2-b110-97fdb8e380fa` 的只读 API 对照证明，产物已持久化而非服务端缺失：

- `GET /api/threads/{thread_id}/state` 返回 HTTP 200；`values` 键包括 `artifacts`，数组数量为 1，类型为字符串，安全虚拟路径为 `/mnt/user-data/outputs/star-surprise.html`。
- 前端 `useStream` 配置 `fetchStateHistory: { limit: 1 }`。实际 SDK 的 `getHistory()` 通过 `POST /api/threads/{thread_id}/history` 读取历史；该响应 HTTP 200，但最新 entry 的 `values` 只有 `messages,thread_data,title`，没有 `artifacts`。
- `ChatBox` 从 `thread.values.artifacts` 设置 artifact context，`ArtifactTrigger` 仅在该 context 非空时显示。因此旧浏览器未出现入口是 history 投影遗漏，不是 artifact owner GET 或 HTML 存储失败。

在 `get_thread_history` 中，仅把最新 checkpoint 的列表型 `artifacts` 投影到 `HistoryEntry.values`，不在更旧 checkpoint 重复携带当前 artifact 列表、不新增状态源或改动 owner-check artifact API。新增路由回归测试，覆盖最新 checkpoint 的 artifact history 投影。

## 固定栈与构建安全

起点为 `b9aa5f0`；起始 tracked 工作树无修改，只有本切片提示词未跟踪。固定 Compose project 为 `insightflow-acceptance-local`，服务为 5 个容器、持有 3 个命名卷，Nginx 入口为 `29384`。Gateway 不挂载仓库代码，必须刷新该服务才能浏览器验证。

构建前只检查路径存在性和忽略规则，不读取配置内容。仓库根 build context 中实际存在 `.reviews/`（206 个直属文件）、`.analytics-demo/`、`.env.analytics-demo`、`config.yaml` 与 `extensions_config.json`；原 `.dockerignore` 未排除这些路径，且 `.env`/`frontend/.env` 已由既有 `**/.env` 规则覆盖。新增 `.env.*`、`config.yaml`、`extensions_config.json`、`.reviews/`、`.analytics-demo/` 排除规则后再构建，避免把本地验收凭据、配置或演示数据送入 Docker build context。未读取其内容。

先将原 Gateway image 保留为本机回滚标签 `iflow-6f3f19-gateway:rollback-b9aa5f0`。仅运行 Gateway build 与 `up -d --no-deps gateway`；构建和服务更新均退出码 0。没有全栈 up/down：其他 4 个容器保持原运行，3 个命名卷仍为 `analytics-demo-data`、`app-home`、`redis-data`；更新后 Nginx `/health` HTTP 200。构建使用原固定 project 的 Compose 文件与 env-file，仅由 Compose 读取运行配置，不输出其值。

## 定点验证

- RED：移除投影修复时，新测试对最新 history entry 访问 `values["artifacts"]` 失败，`KeyError`，退出码 1。
- GREEN：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_threads_router.py -k get_thread_history -q`：16 passed，111 deselected，退出码 0；仅有现存 Starlette/httpx deprecation warning。
- `ruff check` 针对 `backend/app/gateway/routers/threads.py` 与 `backend/tests/test_threads_router.py`：通过。`ruff format --check` 同两文件：2 files already formatted。

## 既有 run 的零模型浏览器复验

在 Gateway 更新后复用同一 owner、既有 thread 与 artifact；无新 thread/run、模型调用或 `POST /runs/stream`。真实 Chromium 结果：登录 HTTP 200，聊天路由命中，`artifact-trigger` 可见且成功点击，`star-surprise.html` 条目可见且成功点击，HTML preview 可见；预览内交互按钮点击后显示内容发生变化。artifact GET 返回 HTTP 206（浏览器成功载入预览）。

脱敏 helper 汇总 `run_stream_posts=0`。它记录 `browser_close completed=False`，但临时 profile 清理为 true，随后按该 helper 唯一 profile 前缀只读查询残留 Chromium 进程数为 0。未保存截图、HTML、消息/模型正文或 artifact 内容；未读取 tool 参数、业务行或私密配置。

## 未覆盖边界与剩余发布门槛

- 真实“小惊喜”欢迎卡片从预填、主题/模型选择、显式 UI 提交到同 run `write_file/present_files` 与 artifact 预览的完整单次流程仍未验收；本轮只复用既有成功 run 验证 UI 投影，不发送新 run。
- Analytics 的 AS-07/08/09/10 完整验收仍依赖各自剩余证据；本切片没有改变该结论，也没有重复模型/分析彩排。
- 默认部署与其他部署拓扑未由固定本机栈验证；本次只做 Gateway 单服务刷新，未重建默认/全栈部署。
- 上游 `surprise-me` skill 已在 Phase 5 删除；当前验证覆盖的是既有通用 artifact 工具链，不代表恢复该技能或其编排行为。
