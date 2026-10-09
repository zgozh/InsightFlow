# 草稿修复最终页面复验

gpt-6-luna/max。主会话已独立读取ChatPage draftThreadId补丁、useThreadChat离开new重置机制、4项DOM回归记录，接受最小隔离方案。只做必要的生产build/deploy与原浏览器probe，不重跑已通过typecheck/tests。

所有权frontend-release自己的构建部署材料/浏览器证据及2026-10-09-catalog-ui-deploy.md。已有前端e1f8需更新ChatPage修复，因此production build一次必要。复用既有build_frontend.ps1/context/cache流程，先同步最新frontend源码关键hash，不带.env或secrets，沿用PS5兼容SHAAPI和BOM。保留旧image回滚。

仅更新29388frontend，认证token从当前环境内存复用，Compose native stderr局部EAPContinue+读LASTEXITCODE，避免已成功部署重跑。Gateway/PG/Redis/Nginx不重建。然后执行既有run_catalog_ui_browser_probe.ps1一次（有限toHaveValue等待已修复）。连续source→edit→metric→edit、旧草稿保护、零runPOST、窄宽可达；不模型、不全suite。真实失败只修直接产品缺陷，记录具体，不继续改断言让它过。

快交newimage/其余ID保持/buildexit/浏览器结果，短记录冻结。当前权限dangerfullaccess/never，禁止sandbox_permissions。
