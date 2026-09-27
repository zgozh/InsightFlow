# Phase 6F3F6：报告卡下载入口与定点 Web 验收

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。先读 `.reviews/phase-06f3f5-fix-01-stack-restore-and-browser-readback.md` 和与本切片直接相关的报告卡、产物 URL 工具、Gateway artifact 路由及测试；不要重读整库或重跑此前有效的套件。

## 目标与已知边界

同一真实 run `63cfc92a-97d9-446d-ad21-58d71ff97821` 的 owner 浏览器已确认：登录、报告索引、分析线程、轨迹面板及 Reviewer 拒绝/通过卡片可见。固定验收 project `insightflow-acceptance-local` 的五个原容器已恢复且健康，三卷未变。此前临时同源 anchor 能触发完成的 Markdown 下载事件，但 Playwright response observer 未捕获响应；因此不能声称 HTTP 200。产品 `ReportCatalogList` 目前只提供“打开对应分析”，没有显式下载动作。

本切片为报告卡增加一个清楚、可访问的“下载报告”动作，复用 `urlOfArtifact({threadId, filepath, download:true})` 与既有 owner-checked Gateway 路由；不新建公开 URL、不改变服务端授权、不读报告正文。现有产物列表的下载按钮是可复用的仓库模式。更新报告卡中“前端构造 URL 会搬走授权边界”的旧注释：安全边界仍由 Gateway 的 `threads:read, owner_check=True` 执行；前端只构造同源受保护请求。

## 实施范围

- 首选仅改 `frontend/src/components/analytics/analytics-catalog-views.tsx`、Analytics zh/en i18n 键与类型，以及一条直接保护报告卡下载动作的 DOM/E2E 测试。沿用已有 Button/anchor/图标、交互尺寸及多语言样式，不重设计报告页。
- `report.thread_id` 与 `report.artifact_path` 均来自已经鉴权的报告列表记录；仍使用公共 `urlOfArtifact` 编码，不手拼路由或开放新 API。不把路径当作授权证明；每次下载仍由服务端 owner check 决定。
- 产品按钮必须能从报告卡直接触发浏览器下载，不能只显示不可点击路径；保留“打开对应分析”的既有动作。
- 不改 Gateway、报告持久化、Agent 运行、模型配置、Compose、依赖或 lockfile；不发模型/Gateway 新 run，不创建账号、报告或数据库记录。

## 最小验证

验证级别 V2（用户可见动作跨前端 URL 契约与服务端授权）+ 一次 V3 定点真实浏览器读回。先用一条稳定测试钉住报告卡的 `href` 经 `urlOfArtifact` 构造、`download=true`、两种语言标签及原有分析入口共存；运行该测试、受影响 TypeScript/ESLint/格式检查。无需前后端全套测试或重新构建 Gateway。

若需让固定栈读取前端变更，只构建并非重建更新 `frontend` 服务；保留 Gateway/NGINX/Redis/PG 容器及卷，按当前状态做有界健康检查。用既有 DPAPI owner、临时 profile 和同一已发布报告做**一次**浏览器点击：

1. 证实按钮存在、其目标为同源受保护 artifact URL，点击后 `download` 事件完成且文件名形状正确；不读取正文。
2. 用同一登录浏览器上下文对同一 URL 做一次 GET，只读取 HTTP 状态/必要安全头，不读取、输出或保存响应正文，从而独立证明实际 HTTP 200（或准确记录非 200）。不要依赖 Playwright 的 download 事件推断状态；既有 owner GET 200/foreign-thread 404 证据不必机械重跑。
3. 如按钮动作失败，按一次性证据定位为 URL/下载路由/浏览器选择器/鉴权哪一层；只修本切片直接引入的缺陷并跑相应定点检查。不要通过重复完整登录流程碰运气。

只在新证据改变结论时最小更新 `docs/acceptance/phase-06d-contract-reconciliation.md` 和 `docs/PROGRESS.md`：如实记载报告 Web 下载是否通过，不能把该单例扩写为 AS-10 的通用数字/evidence 正确性 PASS，也不能把 trace 面板可见写成 AS-09 全阶段 SSE/无思维链 PASS。新文档/注释中文优先。脱敏报告写 `.reviews/phase-06f3f6-report-card-download.md`，列出实际命令/退出码、浏览器下载事件和独立 HTTP 状态、容器/卷是否保持、未验证项。若修改 tracked 文件，提交一个实现提交并保持工作树干净；完成后停在 GPT 复验。
