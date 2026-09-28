# Phase 6F3F18：小惊喜浏览器验收

状态：按预览前置门禁停线；未发送新 UI/model run，待 GPT 独立复验。

## 前置栈与配置

起点为 `afc6763`，开始时除本提示词外没有 tracked 改动。固定 `insightflow-acceptance-local` 仍有 5 个既有容器、3 个命名卷；Nginx 入口端口 `29384` 的 `/health` 返回 HTTP 200。只读 Gateway 配置解析确认精确模型 `deepseek-flash` 与上一切片补入的 `write_file` 仍生效。未重建、重启或清理容器/卷，未读取私密配置值。

## 既有 artifact UI 预览探针

对既有合成 thread `6ce643e7-761c-4ba2-b110-97fdb8e380fa` 做了无模型浏览器检查：登录页与本地登录均 HTTP 200，浏览器到达预期 `/workspace/chats/{thread_id}` 路由。随后等待正常 `artifact-trigger` 入口 25 秒，未出现该入口；检查期间 `POST /runs/stream` 为 0，未发新模型请求，也未尝试绕过该入口直开 artifact URL。没有打开 artifact 预览，也没有检查、输出或保存 artifact 正文；聊天页正常加载可能包含消息历史，本轮未读取或分类其中的 tool args。

浏览器 helper 的临时 profile 已删除；`context.close` 在 helper 的 Playwright context 已退出后报告未完成，helper 未采集异常类别，因此不声称浏览器进程清理已被独立确认。此夹具结果只证明该次浏览器没有呈现可点击 artifact 入口，不据此断言服务端 artifact 不存在：6F3F17 的同 owner artifact GET 仍为 HTTP 200。

## 最小边界判断

源码显示 `ArtifactTrigger` 只在 `artifacts` 非空时渲染；`ChatBox` 从 SDK thread 的 `thread.values.artifacts` 读取并写入 artifact context，界面入口再由该 context 驱动。故本次最窄可证阻塞位于“已存在 thread 的 artifact 状态 → `thread.values.artifacts` → `ChatBox`/artifact context → `artifact-trigger`”投影链，而非 artifact owner GET。仅凭这次浏览器结果无法继续区分 SDK 历史/state 未返回 artifact、或返回后前端未投影；本轮按提示词停在此处，不改生产代码，不再扩大读取或重试。

未满足预览前置条件，因此按门禁没有执行“创建一个小惊喜”新 UI 流程：无欢迎页卡片点击、无新 thread/run、无 `/runs/stream` 请求、无模型请求。旧 run API artifact 证据不外推为 UI 预览证据。原上游 `surprise-me` 技能已在 Phase 5 删除；本轮目标仍只是当前通用 `write_file`/`present_files` 工具链，不恢复该技能。

## 剩余验收清单

| 分类 | 项目 |
| --- | --- |
| 必须验收 | 查明并闭合既有 thread artifact state 到聊天 UI artifact 面板的投影；之后以一次 Chromium 流程验证当前“小惊喜”卡片仅填提示、主题替换、精确模型选择、显式提交、同 run 的 `write_file`/`present_files`、owner artifact 预览及交互。 |
| 可登记残差 | 上游多技能编排式 `surprise-me` 的恢复属于单独产品范围；当前切片不要求与该旧技能体验等价。 |
| 已有证据不重跑 | 6F3F17 的固定配置 `write_file` 加载、一次成功 API run、结构化工具调用和同 owner artifact GET 200；6F3F11 的普通聊天 UI 单次闭环。 |

本轮为单条 UI 前置集成探针；无生产改动、无容器或卷变化、无新 run。后续应转入 Phase 6 剩余验收清单排序，避免围绕同一示例连续增加测试。
