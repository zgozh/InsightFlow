# InsightFlow 产品文档与品牌复核

产品文档定位为个人维护的 InsightFlow 受控经营分析工作台。保留 LICENSE 法律文本与版权署名、`deerflow.*`/`DEER_FLOW_*`/`.deer-flow` 机器接口，以及 LOCAL_TRIAL 中的历史证据；没有声称代码全部从零原创。

本轮补齐分享链接 localhost 仍跳往旧 Vercel 站点、记忆导出文件名前缀、sidecar prompt 的产品称呼、缺失静态 demo artifact 的可见登记，并修正架构文档对指标解析服务的描述。静态 demo 精确文件检查为不存在，全仓精确搜索只在 manifest 中找到文件名；已删除该登记，没有伪造替代产物。分享链接现使用当前 origin，仍受原 owner 身份授权，不提供公共分享服务。

## 检查

- 主会话此前的 About/i18n 定点测试为 9/9，typecheck 通过；本轮未重复运行这两项测试。
- 本轮 thread-sidebar share 与 static-demo 两个 Rstest 文件共 12/12 通过；新增 localhost 回归先观测到旧 Vercel URL，修复后剪贴板收到 `http://localhost:3000/workspace/chats/thread-1`。
- 受影响 TypeScript 文件 typecheck、ESLint 和 Prettier 检查均通过；三个既有 Prettier 失败文件已格式化。
- 本切片涉及的公开文档完成 UTF-8 Markdown 相对链接检查，15 个文件的目标全部存在。
- 本机 Next 的 3000 端口虽有监听进程，但 HTTP 请求 12 秒无响应；本机 landing 首项 reload 超时、另一项通过，故不将其记为通过。部署后在固定入口运行 landing 两项品牌用例，2/2 通过。
- `/`、`/health`、`/favicon.ico` 均返回 HTTP 200。

## 固定入口部署

用户手动恢复后，只读检查确认 `insightflow-acceptance-local` 五容器运行，Gateway、PostgreSQL、Redis healthy。首轮只读前置检查因临时配置检查脚本引用已更换的旧 frontend container ID 而停止；脚本改为按 Compose project/service 标签定位当前 frontend 后，边界检查与 dry-run 通过。

复用 `.reviews/phase-06f3f21-deploy.ps1`，仅将旧 frontend image `18f137c24a8d55f15fde1de30d1bd9f0d367cb6f27b3ed04aa52f2a5bcb07430` 保存在 `rollback-brand-review-20261007`，随后构建并 `up -d --no-deps` 替换 Frontend。新 Frontend container 为 `01fa48766c334580b0ba00545311df7d8eead8966d996c5b39939b353509515d`，image 为 `dd2045e3c8d5afc261290ec19e51b4f1d67d2b9a4f8234d4fd785641c0988dc1`。Gateway、Nginx、PostgreSQL、Redis 容器及三个 volume 均保持原 ID/名称，未发送模型请求。

29384 部署截图（完整页）：桌面 `.reviews/product-brand-review-20261007/landing-desktop.png`，手机 `.reviews/product-brand-review-20261007/landing-mobile.png`。两张图均显示 InsightFlow 产品名与保留的图片来源、许可证 credit。

此切片不改变 AS-01～AS-15 整体 `In progress` 状态。
