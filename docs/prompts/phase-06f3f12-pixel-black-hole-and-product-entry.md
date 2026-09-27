# Phase 6F3F12：像素黑洞品牌首页与真实产品入口

## 角色、起点和交付

你是 InsightFlow 实施子 Agent（gpt-6-luna，max）。主会话只做方案与复验。本轮从当前 `main` 开始；工作树预期只有本提示词这一个未跟踪文件，先核对 `HEAD`、工作树和最近的 `AGENTS.md`，不要假定提示词中的旧 commit 仍是 HEAD。固定上游 tag `upstream-v2.1.0-rc0` 不变。将本提示词与实现一同提交，向主会话报告 commit、文件、定点验证与未验证项，停在 GPT 复验；不自行启动下一阶段。

用户已批准原创红橙色黑洞 favicon，以及参考 DeerFlow 首页像素鹿动效节奏的动态像素黑洞与粒子背景。用户还明确要求：GitHub 远端为 `git@github.com:zgozh/InsightFlow.git`；首页右上角原 Workspace 入口打开此仓库；聊天欢迎页保留“创建一个小惊喜”可编辑示例；Analytics 空页面应让人理解何时有数据、能做什么。不要把演示数据或未验证的模型链伪装成真实数据。

## 先核实的现状

- `frontend/src/components/landing/header.tsx` 的桌面与移动入口指向 `/${lang}/workspace`，但站内 workspace 路由是 `/workspace`；这解释了 404。Hero 的 `/workspace` 主 CTA 是站内进入工作台，必须保留。
- `frontend/src/components/landing/hero.tsx` 目前依赖 WebGL `Galaxy`，外层是暗黑遮罩；用户实际看到几乎纯黑。先确认渲染/降级机制，再用能稳定可见的黑洞视觉取代或收敛该背景，勿仅调高透明度后宣称解决。
- 欢迎示例来自 `frontend/src/core/i18n/locales/{zh-CN,en-US}.ts`，现有四条，点击应只填充可编辑输入框、不自动发送；相关行为见 `frontend/tests/e2e/chat.spec.ts`。
- 受控 Analytics 的目录、指标、报告与审计记录来自真实 API 和当前主体授权。无数据源或无 policy 的普通用户看到空目录是预期；管理员可配置数据源、schema、policy、metric，报告和审计要在实际分析/查询后才会出现。不得为“看着有内容”绕过 principal 隔离或注入假记录。

## 实施设计

### A. 品牌视觉与导航

1. 做一个原创、无第三方版权依赖的红橙色像素黑洞：深色事件视界、非均匀明亮吸积环、适量绕行粒子，图形上可联想到首张黑洞照片，但不是复制照片。首页首屏应当一眼可见，文字与 CTA 始终清楚；不能再是一整块纯黑。参考仓库原有像素/粒子动效的轻巧节奏即可，不新增 Three.js 等重依赖，也不把滚动叙事/整个聊天 UI 重做。
2. 静态轮廓必须在 JS、WebGL、Canvas 动画不可用时仍可见。动画只作为增强：离屏/页面隐藏暂停，`prefers-reduced-motion` 显示静态画面；限制像素/粒子数量与 DPR，避免持续高负载。移动端保留主体轮廓、减少粒子，375px 不横向溢出。不要让装饰画捕获指针或读屏焦点；正文与按钮满足对比度和可见焦点。
3. favicon 用同一视觉语言的简洁 SVG/等效浏览器图标，16px 仍能分辨红橙环与黑色中心。明确检查浏览器实际获取/显示的新图标，移除或覆盖旧鹿 `favicon.ico` 的优先级；不要留下浏览器继续显示鹿的情况。可增加适当的 brand metadata，但不改协议键/内部 deerflow 标识。
4. 首页右上角桌面及移动导航改为清晰的 GitHub 仓库入口，目标 `https://github.com/zgozh/InsightFlow`，新标签打开，带 `noopener noreferrer`；品牌名仍回本站首页，Hero 的“进入工作台”仍走 `/workspace`。若移动导航组件只支持 Next `Link`，在现有组件内做最小正确扩展，不能让外链被当成站内路径。
5. Git 仓库配置：只在确认不存在 `origin` 时运行 `git remote add origin git@github.com:zgozh/InsightFlow.git`；若已有 origin 不同，停止这一步并报告，不覆盖用户配置。验证 `git remote get-url origin`。**不得 push、fetch、pull、force 或改分支历史**；remote 是本地仓库配置，不出现在代码提交里。

### B. 聊天示例与 Analytics 空态

1. 在现有欢迎示例中补一条中英对应的“创建一个小惊喜 / Make a little surprise”。点击只填充可编辑提示词，用户可先改主题后发送；示例围绕沙箱生成可预览的交互式 HTML 小页面，不暗示必然成功、不自动执行或绕过现有工具流程。保留主流聊天布局，不重做输入框。若五条卡片在小屏拥挤，可用现有换行/滚动样式做最小调整，不删除已有重要示例。
2. 核实分析会话、数据源、指标、报告和审计历史各空态。仅在现有文案会误导用户时修改：普通用户解释“尚无获授权数据源/请管理员配置”；管理员页面指向现有创建/策略操作；指标说明配置后可用；报告/审计说明真实分析、查询后生成；分析会话入口保持可新建。错误、403、空集合不能混为一谈。中英文同步，仍走现有 i18n；不新增假数据、自动授予、数据库种子或管理 API。
3. 若某个页面的空态已经准确，保留并在报告中说明；不要为了“覆盖清单”制造改动。用户问“能否互动”，最终报告需简短区分管理员可配置、普通用户可查询/分析的前提，以及历史/报告何时出现。

## 边界与验证

- 仅改这轮直接相关的首页/导航/图标、欢迎示例、必要的 Analytics 空态和对应测试/文档。不改后端 SQL 授权、认证、数据库、分析运行时或固定验收栈数据；不加依赖或 lockfile 改动。新注释与自有文档中文优先，用户文案中英齐全。
- 按比例工程原则：视觉/路由/i18n 属 V2，首屏、图标和两个入口的真实浏览器表现属定点 V3。先做受影响的类型/格式与直接相关单测；再用 Playwright 定点确认首页桌面及 375px、GitHub 外链、工作台 CTA、聊天示例填入、Analytics 关键空态。检查 `prefers-reduced-motion` 与非 WebGL 静态轮廓。**不要机械跑全量后端、全量前端或所有 E2E**。
- 如果需要让用户当前 `insightflow-acceptance-local` 页面看到新前端，先确认现有 Compose 入口与容器状态；只重建/替换受影响的前端服务，保留数据库、Redis、Gateway、Nginx 和卷，不执行 `down --volumes` 或新建一套栈。说明是否实际部署以及浏览器缓存/favicon 刷新方式。若不能安全局部重建，停下报告，不擅自重建整栈。
- 交付前查看精确 diff、`git diff --check`、提交范围和工作树；更新 `docs/PROGRESS.md` 的本切片事实，不宣称 Phase 6 或全局 AS 已完成。报告测试命令与真实结果，不以截图/合成响应冒充真实 Agent→沙箱→HTML artifact 链；该链若未实测须明确写未验收。
