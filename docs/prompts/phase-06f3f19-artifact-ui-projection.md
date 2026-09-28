# Phase 6F3F19：用既有产物闭合聊天 UI 投影

6F3F17 已有成功 `deepseek-flash` run `a7b51a20-0c59-4eff-9adf-c64bdb256d61`，thread `6ce643e7-761c-4ba2-b110-97fdb8e380fa`；工具调用含 `write_file`/`present_files`，同 owner 的 `/mnt/user-data/outputs/star-surprise.html` artifact GET 为 200。6F3F18 浏览器登录并进入该聊天页，但 25 秒内无 `artifact-trigger`。本切片只定位和修复**已有产物 → thread state → UI 入口/预览**的最短断链；不重新跑模型，不修改“小惊喜”技能/提示词，不开展全局测试。

1. 起点 `b9aa5f0`、干净工作树。先以既有 owner 认证对同一 thread 做**只读状态 API**，仅输出 `values` 键集合、artifact 数量、虚拟路径/类型的安全摘要，不输出消息正文、tool args、凭据或 HTML 正文。并核对 artifacts 的现有 thread state 更新/持久化契约、前端 SDK 取得该 state 的时机、`ChatBox`→artifact context→`ArtifactTrigger` 条件。区分“服务端 state 缺 artifact”与“state 有 artifact 但前端漏投影”，不得因 UI 空白直接猜原因。
2. 若确认产品缺陷，在原有状态或前端数据流上做**一处最小修复**。优先沿当前 artifacts 契约复用已有 owner-scoped artifact API 和现有 UI；不新建第二状态源、新 artifact 存储、兼容层或通用框架。若旧 run 无法从既有契约恢复但新 UI run 可正常显示，先报告事实，不为单次直连测试构造异常兼容路径。
3. 为确认的用户可见回归增加一条能长期保护该契约的定点测试。V2 只跑受影响前端/后端测试、类型或 lint。只有必须部署前端/Gateway 才能验证旧 artifact 入口时，最小刷新相应服务，保留固定 `insightflow-acceptance-local` 的其他容器、三个卷及 `29384`；禁止全栈 `up/down` 和无关全套测试。
4. **零模型请求**复验：同 owner 浏览器打开已有 thread，验证 artifact 入口出现、正常预览可见及一个简单点击交互。预览 HTML 的检查可在浏览器进程内进行，但报告只写安全摘要，不存正文。若预览成功，本切片即停；新的“小惊喜” UI 提交留到下一条里程碑且最多一次。若仍失败，记录最早可证断点，不循环 Playwright 等待或重建环境。

报告写入 `docs/acceptance/phase-06f3f19-artifact-ui-projection.md`，同步 `docs/PROGRESS.md`。提示词与必要修复单独提交，工作树干净，不 push。结尾用最多五行更新**全项目剩余发布验收门槛**（真实小惊喜 UI 单次流程、经营分析真实链已有哪些证据/缺哪些、默认部署、已知残差）；不得把全量测试自动列成每轮常规门禁。完成后停在主会话复验。
