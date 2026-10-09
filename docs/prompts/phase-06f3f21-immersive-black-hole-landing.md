# Phase 6F3F21：首页黑洞视觉返工

用户明确否定现有“右侧小块像素环 + 纯黑背景”和自创像素 favicon。目标是一个**真正占据首屏背景**、有高像素密度和动态粒子层次的黑洞体验；标签页 favicon 使用人类首张黑洞影像 M87* 的真实照片，而不是画出来的图标。首页仍以中文为主，工作台和认证页面不借机重做。起点 `a678d54`；未跟踪的 `docs/prompts/phase-06f3f20-surprise-user-flow-and-release-triage.md` 是暂停的后续切片，保留不改、不提交到本切片。

## 设计与来源

1. 先对照 `upstream-v2.1.0-rc0` 的 `frontend/src/components/landing/hero.tsx`：原首屏用铺满背景的 `Galaxy` 星场和鹿形遮罩 `FlickeringGrid`，不是旁边摆一个插画。当前 `frontend/src/components/ui/galaxy.jsx`、`flickering-grid.tsx` 及 `ogl` 依赖仍在。可复用上游星场、可见性/减动效机制与合适的组件，但不能把鹿遮罩带回来。黑洞本体做原创的高分辨率动态背景，不沿用现有粗矩形像素环。
2. 黑洞参考 NASA 的[吸积盘、光子环和引力透镜说明](https://www.nasa.gov/universe/nasa-visualization-shows-a-black-holes-warped-world/)以及[模拟可视化](https://svs.gsfc.nasa.gov/14619/)：暗核心、非均匀红橙/金色吸积环、被扭曲的背侧光弧、向内运动的粒子与微弱星场。追求**视觉可信的艺术模拟**，不宣称物理精确 ray tracing；不复制外部 demo 代码/素材。首屏背景占满容器，黑洞在桌面占明显视觉面积、位于文案后方偏右或中央，粒子穿过首屏边缘；不要再出现独立的 `hero-art` 右侧框。手机上仍是同一背景，控制主环与文字的遮挡，确保标题、说明和 CTA 清楚可读。
3. favicon 必须是 2019 年 EHT M87* **真实照片**的局部裁切，不是 AI 生成/手绘近似。首选 [ESO 官方 `eso1907a` 图像](https://www.eso.org/public/images/eso1907a/)；如果使用其已有方形裁切的可信派生图，必须追溯到该官方原图。作为本地静态资源交付，不在运行时依赖外部 URL。把当前 `layout.tsx` 中指向自绘 `/favicon.svg` 的 metadata 与可能被浏览器回退使用的旧 `/favicon.ico` 一起处理，避免标签栏继续出现旧鹿或像素图。为小尺寸选清晰可辨的裁切；不要将大尺寸原图直接当 32px 图标下载。
4. ESO 页标注图像 credit 为 **EHT Collaboration**；[ESO 使用政策](https://www.eso.org/public/outreach/copyright/)说明一般为 CC BY 4.0 且须清晰署名。首页页脚增加可见的照片 credit 与原图/许可证链接，并在项目资源说明中记录来源、裁切/缩放与许可证；不要暗示 EHT/ESO 为本项目背书。若具体源文件另有更严格条款，先停下报告，不擅自使用。动画是自有代码，其来源只需在设计说明标记为“参考科学可视化”，不要把 NASA 模拟视频直接嵌入生产站点。

## 实施边界

- 保留当前首屏中文价值主张、工作台 CTA、GitHub 仓库链接及后续两个产品段落；只改首屏视觉层、favicon/必要 credit。颜色仍以黑/暖橙/金为主，但必须有空间深度，不是一块纯黑。可删除被替代且无引用的 `pixel-black-hole.tsx`、旧自绘图标；不增加新 JS/渲染依赖，优先复用现有 Galaxy/Canvas/WebGL 基础。
- 动画随页面不可见、后台标签或 `prefers-reduced-motion` 暂停/静止；低性能移动端限制像素比和粒子数，不持续拉高 CPU/GPU。无 WebGL/Canvas 时仍有完整的静态背景，不能退回纯黑。焦点、对比度与 CTA 点击区域不被动效层挡住；动画层对辅助技术隐藏。
- 验证按 V2：受影响组件定点测试、类型/格式/静态检查；真实 Chromium 只看首页 1280×720 与 375×812、favicon 真正获取/解码、减动效静态状态、无横向滚动与 CTA/GitHub 可点击。**必须保存这两张完整页截图供主会话目视审查**；不要只凭 DOM 断言称“有设计感”。不跑全仓 Rstest、全量 Playwright 或无关后端/Docker 数据库测试。
- 只有本地视觉与门禁通过后才可仅刷新固定验收项目 `insightflow-acceptance-local` 的 Frontend，使用 `--no-deps` 保持 Nginx/Gateway/PostgreSQL/Redis 四个容器、三卷和 `29384` 入口不变；旧 Frontend 镜像保留可回滚。若当前 Compose 渲染端口与运行栈漂移，不做全栈 `up`。部署后确认 `/`、`/health` 与 favicon 200，重复一次桌面/手机截图以证明部署版本。不要发模型请求。

产出 `docs/acceptance/phase-06f3f21-immersive-black-hole-landing.md` 和必要资源署名说明，更新 `docs/PROGRESS.md`。生产代码与文档一个聚焦提交，工作树干净，不 push。报告写明照片来源/许可证、视觉取舍、桌面/手机截图路径、动效退化、门禁与固定栈变更；停在主会话的**目视**复验。若首次视觉成果仍像侧边插画或低质像素环，不要声称验收通过，应在提交前改到符合上述画面关系。
