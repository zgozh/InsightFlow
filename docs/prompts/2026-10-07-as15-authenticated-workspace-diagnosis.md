# AS-15 已登录分析入口有界诊断与修复

执行者：用户指定 `gpt-6-luna` / max。主会话已独立审查品牌修复源码与29384双截图，品牌切片接受。整体AS01～15仍推进，本切片只解决里程碑1剩余浏览器入口。

## 环境和所有权

复用 `as01-as15-1bf6932f3abd` 四服务隔离栈，Nginx `127.0.0.1:29385`；临时A/B账号的DPAPI仅在该唯一目录，A analysis线程 `9e080128-aedc-44f5-9ece-4bf75692021e`、B chat线程已存在，APIowner/run/events/artifact拒绝矩阵已有有效证据，不重复注册/seed/模型。该栈当前Frontend仍是黑洞版本（旧image18f137），不要求先品牌刷新，不碰29384或旧栈。

独占临时安全诊断runner、报告 `docs/acceptance/2026-10-07-as15-workspace-diagnosis.md`、原AS01/15报告与PROGRESS/矩阵必要状态。只在明确复现的局部产品缺陷时允许改直接涉及的组件/hook/路由和对应回归，先报告根因再实施；不可预先调整auth/security/contracts/Next配置或禁用认证。

## 第一步：排除旧runner断言错误

旧 `.reviews/as01-as15-1bf6932f3abd/browser_probe.cjs` 只监听 `/api/threads/{id}`，而SDK经Nginx `/api/langgraph/threads/{id}`请求；composer用英文placeholder正则，未读取实际语言；固定5秒sleep。`ownThreadApiStatus=null` 和 `composerVisible=false` 因此不是充分产品缺陷证据。

先定点读前端 analysis路由、输入组件的真实data-testid/role、`useThreadMetadata`的实际client路径和AuthProvider/布局门禁，确定匹配规则。不读整套threads/hooks或全部架构历史，只读涉及符号。主会话已读analysis路由：metadata `isLoading`才显示loading，true marker才挂ChatPage。

## 第二步：一次有界真实浏览器证据

安全读DPAPI经stdin传账号；使用真实独立context登录并确认/me200。建立request/response/pageerror监听后导航A分析线程与analysis/new，等待**真实DOM条件**（loading/analysis状态/输入/错误之一）而非固定sleep，最长30秒；没有模型POST。优先一次browser session完成路径对照。

仅记录：同源请求的path/status/成功失败类别（不打印query/body/token）、相关DOM testid/role存在与loading/error布尔、URL path、JS error类别及可安全归类的文件/行号、document readyState/资源requestfailed类别。可对本栈完全合成无客户数据页面截一张本地诊断图用于目视，但不把登录凭据/消息正文保存。禁止打印cookie、任意整页HTML、模型/用户正文/配置。

明确处理没有配置模型的情形：若现行应用应给模型缺失状态，则按界面可操作性和既有contract判断；不能为了测试随意填真实API key或发模型。可以在隔离配置添加不调用的显式合法测试模型作为单变量探针，但先有证据证明缺模型导致该状态；对只读诊断不修改生产模板。

检查A own metadata请求与UI结果对照、anonymous跳登录与B foreign路由拒绝状态；不要把“英文placeholder没匹配”或路径监听漏计当认证/挂载失败。

## 结论与最小修复

- 若修正runner后workspace实际可见：这是验收夹具错误，不改产品代码，更新原报告旧未证实断点。AS01/15按场景全部条件核对，符合才mark通过。
- 若真缺陷：说明具体输入→断点代码→可重复观察，新增最小行为回归先RED，再最小补丁，直接受影响lint/format/typecheck/test。无需全套frontend/backend。
- 只有产品代码改动需要刷新29385**Frontend-only**，旧镜像保留；配置/品牌生产更新无需触及29384。实际新镜像可复用已builddd2045作为无关品牌最新production版本，但产品修复则需其新build。其他三个容器/隔离SQLite和卷不动。
- 一次真实浏览器复验明确登录→analysis工作台可操作（不发送）和权限状态。Report隔离compose是defaultbase+名称/镜像/挂载overlay，不伪称原makeup实跑；readiness原脚本测试证据17pass已有效。

V1为局部产品回归，V3为上述真实浏览器AS01/15收口，取最小足够检查。主会话已使用systematic-debugging原则：先根因证据再修复；不做盲等、连续模型/容器重试。约60秒实际进度，够证据即实施/返回，别把一条runner改动变多轮大报告。

最后返回实际diff/命令/HTTP/DOM条件、安全恢复路径与是否完整满足AS01/15。不commit/push；冻结后主会话独立复核并自动派分析角色/evidence里程碑。
