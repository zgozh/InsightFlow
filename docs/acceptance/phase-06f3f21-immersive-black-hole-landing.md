# Phase 6F3F21：沉浸黑洞首页本地交付

日期：2026-10-07。起点：`a678d54`。实施者：用户指定的 `gpt-6.1-sol` / medium。状态：源码和本地定点验证完成；主会话已独立阅读 diff、动效/生成脚本/credit，并目视本地和部署版桌面/手机最终截图，接受本地与部署首页。主会话另只读确认五容器running、三项health healthy、health/favicon200。未提交、未 push；整体发布仍 In progress。

## 变化与视觉取舍

原双栏 `hero-art` 与粗像素黑洞已移除。首屏使用铺满容器的原创细颗粒背景，暖金橙红吸积盘斜穿首屏，背侧透镜弧绕过暗核心，外围尘埃和星场延伸至边缘。文案与两个产品段落保持既有中文；文案局部暗遮罩、暖金 CTA 和手机构图位移保证可读与可点击。

背景 SVG 是外部图片而非内联 DOM（1,688,093 字节；gzip 235,377 字节）。生成脚本固定种子可复现。Canvas 仅叠加流动颗粒，约 30fps，桌面 850 / 手机 320 颗粒，像素比上限分别 1.5 / 1。使用既有 `useRenderActivity` 在离屏、后台标签、减动效时停止循环；不支持 Canvas 或禁用脚本时完整静态底景仍可见。动效层隐藏于辅助技术并禁用指针事件。无新 JS/渲染依赖。

favicon 来自真实 EHT M87* 照片，PNG 32px 与兼容 ICO 均已替换旧资产。可见页脚署名 **EHT Collaboration**，附原图、CC BY 4.0 与裁切缩放说明。来源和生成信息见 [资源说明](../../frontend/public/images/BLACK-HOLE-CREDITS.md)。动画只参考科学可视化，不复制外部代码/素材，不宣称物理精确模拟。

## 验证（V2）

命令从 `frontend/` 执行，宿主 pnpm 经 `python ../scripts/pnpm.py`。本地 Webpack dev：`SKIP_ENV_VALIDATION=1 DEER_FLOW_AUTH_DISABLED=1 python ../scripts/pnpm.py dev`，监听 `http://localhost:3000`，未修改配置文件。

- `exec eslint` 指定 Hero、BlackHole、Footer、layout、三份 branding 词条与 landing.spec：通过。初次 BlackHole 存在一条无用 eslint-disable 警告，已删除，受影响文件复验无警告。
- `typecheck`（`tsc --noEmit`）：通过。
- `exec prettier --check` 上述八个 TS/TSX 文件：通过。
- `exec rstest run tests/unit/core/dom/render-activity.dom.test.ts`：3/3 通过，覆盖后台标签、离屏、减动效与清理。
- `PLAYWRIGHT_SKIP_WEB_SERVER=1 PLAYWRIGHT_BASE_URL=http://localhost:3000 exec playwright test tests/e2e/landing.spec.ts --workers=1 --reporter=list`：首轮 9/10 通过；CTA 测试在首次 `/workspace` 开发编译时超过默认 30 秒。保留原导航断言，编译后以 `--grep 'hero call to action' --timeout=90000` 定点重跑：1/1 通过，18.3 秒完成。
- 手机构图/底景亮度收敛后，`--grep 'fills the hero'` 定点通过并重新保存桌面、手机完整页截图。其余有效证据未重复全量运行。
- Chromium 已检查：中文内容、1280×720 与 375×812 全屏背景、320/375/390 无横向滚动、桌面/手机 GitHub 外链属性与菜单点击、工作台 CTA 点击及最终路由、PNG favicon HTTP 200 / 解码为 32×32、兼容 ICO HTTP 200、无 Canvas 静态背景、减动效与离屏停帧。
- `git diff --check`：通过。旧 PixelBlackHole / favicon.svg 生产引用检索为空。启动 Next 自动重写的 `frontend/AGENTS.md` 已恢复原内容。

完整页截图（本地版本，尚非部署版）：

- 桌面：`D:/develop/workspace/InsightFlow/frontend/test-results/phase-06f3f21-desktop-1280x720.png`
- 手机：`D:/develop/workspace/InsightFlow/frontend/test-results/phase-06f3f21-mobile-375x812.png`

初始本地验证阶段未运行全仓 Rstest、全量 Playwright、后端测试或生产构建；当前改动未变更依赖、路由或构建配置。随后 Frontend-only 部署已成功执行镜像内实际 production build，此构建证据与初始本地检查分别记录。

## 固定栈与剩余证据

`docker ps --format '{{.Names}}'` 失败：Docker Desktop Linux engine 的 `//./pipe/dockerDesktopLinuxEngine` 不存在。未启动或重建固定验收栈，未执行 Compose `up`，未替换 Frontend 镜像，未动 Nginx/Gateway/PostgreSQL/Redis、卷或 `29384` 入口。本地首页 HTTP 200。

生成脚本补做 backend Ruff：首次 E501（长 SVG 字符串）按相邻字符串拼接修正，`ruff check` 和 `ruff format --check` 均通过。重生成资产 SHA256 前后相同：`0194c4fc816bc40bdca007c3e9e632eeb20037497410b15a0cec3e2507fd29f9`，此前视觉与前端验证仍有效。

续接时 Docker Desktop hidden 一次启动成功，Engine 29.1.2 已就绪，原 PostgreSQL/Redis 已恢复 healthy；启动原 Gateway/Frontend/Nginx 的命令被主机自动审批策略拒绝（`blocked by policy`），没有执行。用户随后手动恢复这三容器，健康核对通过后，已按原约束完成固定项目 Frontend-only build/up（`--no-deps`、旧镜像可回滚）。新Frontend `1e2c37bbcd3992a4d8955c13c1e81e04892d075c42028f12cd063baa7a253e97`，另外四容器ID及三卷不变。部署 `/`、`/health`、favicon均200，favicon解码32×32；桌面/手机无横向溢出。

部署完整页截图：`D:/develop/workspace/InsightFlow/.reviews/phase-06f3f21-deployed-desktop.png`、`D:/develop/workspace/InsightFlow/.reviews/phase-06f3f21-deployed-mobile.png`。准确命令、回滚image/新image与用户恢复记录见 [6F3F20记录](phase-06f3f20-surprise-user-flow-and-release-triage.md)。6F3F21本身没有模型请求，另一个6F3F20切片执行了一条真实欢迎卡片run；不宣称整体Phase6/发布验收。
