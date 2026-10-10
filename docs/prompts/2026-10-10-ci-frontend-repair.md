# 前端 CI 失败集中修复

实施者 gpt-6-luna/max。读取前端与目标目录AGENTS。拥有frontend/及 docs/acceptance/2026-10-10-ci-frontend-repair.md，不可写backend/或根文件，另一worker修后端。

fa0213c Frontend Unit Tests run38019134104 1failed/1502passed：tests/unit/components/ui/animation-scheduling.test.ts 仍检查旧Galaxy Hero实现。证据 .reviews/ci-20261010/job-114115993613.txt。核对现黑洞组件真实reduced-motion/offscreen/RAF行为；不要改回旧图，不skip/xfail，不用无保护价值的源码字符串替代真实行为（可使用已有行为测试证据并移除过时重复断言，须说明覆盖在哪）。如确认实际动画调度bug则最小修复并直接行为回归。

Lint Check run38019134102前端Prettier失败8文件，列表 .reviews/ci-20261010/job-114115993872.txt：只格式化列出8文件（AGENTS.md/素材署名/scheduled-tasks页/4E2E/feature API测试），不整仓format，不改CLAUDE。格式文件不触发E2E重跑。确认实质diff只是格式。

V1：运行直接受影响动画单测/相关行为测试，8文件和修改测试的Prettier检查、受影响TS lint。无需重复build或运行完整1503suite；新提交Linux CI作为V3证明。禁止workflow屏蔽gate，禁止Docker/新账号/模型调用。现有pnpm依赖可用，脚本scripts/pnpm.py，不安装或改lock。

先消息返回根因与生产是否需改；完成冻结返回实际diff/精确检查结果，不commit/push，由主会话审查后自动交付。权限遵守tool审批。
