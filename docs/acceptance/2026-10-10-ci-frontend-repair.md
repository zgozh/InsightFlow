# 前端 CI 修复验收记录

日期：2026-10-10

## 根因与改动

Unit Tests run `38019134104` 中，1503 项有 1 项失败：`animation-scheduling.test.ts` 仍从 `hero.tsx` 搜索旧 Galaxy 实现的源码字符串。当前首页 Hero 已委托给 `BlackHole`；组件使用 `useRenderActivity(sceneRef, false)`，仅活动时启动 RAF，并在 effect 清理时取消帧。因此这是过时的静态断言，生产动画代码无需修改。该文件只有这一项 Galaxy 断言，已移除。

当前行为由以下测试覆盖：

- `tests/unit/core/dom/render-activity.dom.test.ts` 验证页面隐藏、元素离屏、减少动态效果偏好及清理行为。
- `tests/e2e/landing.spec.ts` 的 “pauses hero particles for reduced motion and when scrolled offscreen” 验证当前黑洞背景在减少动态效果和滚动离屏时停止动画。

Lint Check run `38019134102` 报告八个文件未满足 Prettier。已仅格式化 CI 列出的八个文件；代码行为未改。

## 定点验证

- `python scripts/pnpm.py rstest run tests/unit/core/dom/render-activity.dom.test.ts`：3 项通过。
- 对 CI 列出的八个路径运行 `python scripts/pnpm.py exec prettier --check ...`：全部通过。
- 对六个受影响 TypeScript 路径运行 `python scripts/pnpm.py exec eslint ...`：通过。
- `git diff --check -- frontend`：通过。

没有改动生产组件，因此未重跑 landing E2E、完整 1503 项前端单测或构建；提交后的 Linux CI 负责最终集成验证。本次未提交或推送。

## CI 证据

- `.reviews/ci-20261010/job-114115993613.txt`：动画过时测试失败及单测汇总。
- `.reviews/ci-20261010/job-114115993872.txt`：Prettier 八文件失败清单。
