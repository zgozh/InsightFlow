# Phase 6F3F20：小惊喜用户流程收口与发布验收排序

起点 `a678d54`。6F3F17 已证实 `deepseek-flash` + 既有 `write_file/present_files` 可生成 HTML；6F3F19 已修复 history 的 artifact 投影，旧产物在真实浏览器中能预览并点击交互。当前仅缺**从欢迎卡片实际提交**的单次用户流程证据。完成后必须切换到其他发布门槛，不在同一示例上追加多轮测试。

## 唯一用户流程

1. 确认固定 `insightflow-acceptance-local` 入口 `29384` 和当前配置中的精确模型 `deepseek-flash`、`write_file` 可用。保持五容器/三卷，不重建，不改配置，不触碰既有会话/产物。
2. 使用真实 Chromium 与既有安全登录 helper，从普通聊天欢迎页点击“创建一个小惊喜”；确认按钮只预填可编辑文本，不自动发送。将主题占位符改为“星空”，选定精确模型 `deepseek-flash`，**只点击一次**发送。请求监听须在点击前设置，并异步等待 `/runs/stream`、响应及有界 run 终态；绝不使用点击后立刻读零计数的旧夹具。记录 thread/run/`Content-Location` 的安全标识、HTTP 与状态，不打印 cookie、密钥、自由文本或 HTML。
3. 同 run 有 `write_file/present_files` 与 artifact 时，在聊天 UI 正常入口打开预览并点一次交互；若模型只回文字、UI 未提交或产物缺失，记下最早可证断点，不重复点击或再发模型请求。此前 API/旧产物证据不能替代此新流程，也不因单次模型非确定性结果臆造产品缺陷。
4. 这是 V3 的**一条真实用户旅程**，不跑全仓 pytest、Rstest、全量 Playwright、全量 build、真实数据库套件或 Docker 全栈重建。若发现明确局部缺陷，只做事实定位并报告，本切片不在同一轮追加付费重试或扩大修复；是否另开修复由主会话决定。

## 交付与节奏

写 `docs/acceptance/phase-06f3f20-surprise-user-flow-and-release-triage.md` 并同步 `docs/PROGRESS.md`。报告前半只记录单次浏览器流程各边界事实；后半给出最多 5 项**按风险排序的剩余发布验收门槛**，逐项标识“已有证据 / 尚缺证据 / 是否阻断个人简历演示”，不得笼统要求重跑全套。提示词与报告同一提交，忽略目录存临时 runner，工作树干净，不 push；完成后停在主会话复验。下一轮主会话将切换到排序最高的**其他**门槛，不再为小惊喜例子无限开切片。
