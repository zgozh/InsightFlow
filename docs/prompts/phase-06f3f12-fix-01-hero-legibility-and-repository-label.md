# Phase 6F3F12 Fix 01：首页阅读层级与仓库入口命名

## 起点与原因

从已提交的 `2b46a26` 开始；先核对 HEAD、工作树和本提示词未跟踪状态。主会话复验 `frontend/test-results/phase06f3f12-landing.png` 与提交 diff 后发现两处确定问题：桌面/移动导航的实际目标是 GitHub，却仍显示 `Workspace`；1280×720 截图中红橙吸积环横穿产品名、标题和正文，正文可读性与视觉层级不足。Fix 01 只处理这两个问题，不重做 6F3F12 其他功能。

## 修复要求

1. 首页右上角桌面及移动入口明确显示 `GitHub`（或等价的「GitHub 仓库」中英文案），仍指向 `https://github.com/zgozh/InsightFlow`、新标签及 `noopener noreferrer`；不要改 Hero `/workspace` 站内 CTA。同步调整只直接相关的断言。不要再用“Workspace”作为 GitHub 链接名。
2. 用现有像素黑洞组件调整首屏构图，使桌面宽屏上的标题、说明和 CTA 处在稳定清晰的阅读区域，吸积环成为醒目的独立视觉焦点而不是穿过文本。建议桌面做左文右图或等效分区；移动端可上下布局/更强遮罩，但必须看得到黑洞主体，同时不盖住文字、不横向溢出。保留用户已批准的红橙像素环、粒子、静态降级、减少动画、离屏暂停与原有文案，不添新依赖或重型渲染库。焦点、触控目标和 CTA 保持可用。
3. 用真实浏览器分别截取约 1280×720 与 375×812 的最终首页，**目视**核对文本没有与明亮像素环重叠、黑洞仍清晰、导航语义正确；必要时只做一次小幅位置/遮罩收敛。截图无需提交，可在报告给出路径。不因本修复重建固定 Docker 栈。

## 范围与验证

预计仅修改 `frontend/src/components/landing/{header,mobile-nav,hero,pixel-black-hole}.tsx` 中必要文件与直接相关的 `frontend/tests/e2e/landing.spec.ts`，更新 `docs/PROGRESS.md`，并提交本提示词。若不需动某文件就不动。V1/V2 定点：受影响的类型/格式检查、landing 的导航与首屏 Playwright 用例、桌面/移动截图；既有 6F3F12 其他通过证据继续有效，不重跑全量前端、后端、分析数据库或真实模型。最终审查 diff、`git diff --check`、提交范围、工作树与固定 tag；单独 Fix 01 提交，停在 GPT 复验，不 push 或开启下一阶段。
