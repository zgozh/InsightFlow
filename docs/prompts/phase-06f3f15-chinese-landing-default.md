# Phase 6F3F15：首页中文默认展示

## 起点与目标

从 `3e02170` 之后的干净 `main` 继续，先核对 HEAD 与工作树（预期只有本提示词未跟踪）。用户明确要求作为中文优先的个人简历项目，`/` 首页展示文本默认中文。此切片只改**首页**，不把全局 `DEFAULT_LOCALE` 或工作台用户语言偏好一起翻转。现有英文词条仍保留，首页继续静态渲染，不读 cookie。

已核对现状：`frontend/src/app/page.tsx` 显式用 `DEFAULT_LOCALE=en-US`，并把它传给 `Header`；中文品牌/治理/工作流文案已在 `analytics.zh-CN.ts`。`frontend/src/components/landing/footer.tsx` 目前硬编码英文品牌词条和一句英文口号，因此只改 page/header 不足以达到「首页全部中文」。根布局 `html lang` 与 metadata 是全站共享，不要为了单页改动全站默认语言。

## 最小实施

1. `app/page.tsx` 使用页级常量 `"zh-CN"` 获取词条并传给 Header；首页容器显式 `lang="zh-CN"`，让页内读屏语言准确且不触碰其他路由。Hero/两个产品段落和图标标签继续复用现有中文词条、原布局和像素黑洞，不另写一套展示文案。
2. Footer 改为复用传入的页级品牌词条；把原英文口号纳入现有 branding 双语资源（中文「源于开源，回馈开源。」、英文保留原义），保证默认首页的口号、派生说明、许可说明都显示中文。避免页脚单独重新读取 cookie 或硬编码一份中文/英文分支。
3. 若首页搜索/分享元描述仍继承全站英文 tagline，只在首页 page 层覆盖为已有中文 tagline；不要改全站 `layout.tsx` 的默认 `html lang`、metadata 或工作台 locale 解析。产品名 InsightFlow、GitHub 品牌名、MIT/DeerFlow 正当上游署名可保留原名，不做机械汉化。
4. 更新直接受影响的首页断言；真实浏览器在 1280×720 与 375×812 核对页头「GitHub 仓库」、Hero 中文标题/说明/CTA、下方两个区块及 Footer 中文，确认黑洞仍可见、中文换行不覆盖内容也不横向溢出。英文词条与现有工作台语言选择仍应可用。

## 验证与部署边界

V2：仅运行首页相关 Playwright、类型检查、受影响文件格式/静态检查；不跑全量前后端、数据库或模型。为让用户当前本机页面可见中文，若固定 `insightflow-acceptance-local` 五容器仍是预期且健康，参照 6F3F13 的**已验证** frontend-only 构建/替换过程更新 Frontend，先保留旧镜像回滚点，绝不对漂移的 Nginx 端口执行无服务限定 Compose `up`，不重建 Gateway/数据库/Redis/Nginx、不删卷。然后经真实 Nginx 做上述首页定点浏览器检查；环境不满足则源码提交并报告「尚未部署」，不要强行恢复/重建整栈。

新注释中文优先。提示词、源码、直接受影响测试与 `docs/PROGRESS.md` 一同提交一个有边界的切片；报告实际命令/计数、部署与否、截图路径、未验证项，检查 diff/工作树/固定 tag 与 lockfile；不 push。停在 GPT 复验，不启动下一切片。6F3F14 的单次 UI 提交仍无 Gateway run 证据，不能因本轮中文首页而改写为「小惊喜真实链通过」。
