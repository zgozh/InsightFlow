# Phase 4 实施提示词：InsightFlow 产品工作台

你现在执行 InsightFlow Phase 4。不要凭本提示词摘要自由发挥；以下两份文件才是完整规格和施工主线，
必须从头到尾读取并逐项执行：

1. `docs/architecture/phase-04-insightflow-product-workspace.md`
2. `docs/superpowers/plans/2026-09-22-phase-04-insightflow-product-workspace.md`

同时读取根 `AGENTS.md`、`backend/AGENTS.md`、`backend/app/analytics/AGENTS.md`、
`frontend/AGENTS.md` 以及实际修改目录下更深层的全部 `AGENTS.md`。冲突优先级为：本提示词明确裁决
> Phase 4 architecture > Phase 4 plan > 模块指南 > 既有习惯。发现真正不可兼容的冲突时停止报告，
不要静默选边。

## 1. 已批准起点与裁决

- 起点：`7bd21d7721e3caf3cc7cc1b90bb9d3b51b7b2d8a`。
- 固定 tag：`upstream-v2.1.0-rc0`，commit/tree 不得移动或重写。
- Phase 3 通过复验。
- 接受 `query_business_data` 的额外字段在模型 schema 层排除；不改通用工具装配追求行为级报错。
  伪造 principal 不能改变 runtime principal 的测试必须保留。
- 采用单个 Phase 4，不再拆 4A/4B；按计划内任务顺序 TDD，最终只交一个实现提交。

## 2. 强制可行性门禁

生产代码前先完成计划 Task 1。重点确认：可信 runtime 身份/thread/run、subagent 真正看不到 report tool、
artifact ownership、消息历史可重建 trace。若门禁失败，保持工作树仅有本轮三份规划文档，不提交实现，
只给出证据和一个最小 seam 建议；不要提供多个选择等待 GPT。

门禁成立后直接继续全部实施，无需再次询问 GPT。

## 3. 不得扩大的边界

- 不新增 npm/Python 依赖，不改 lockfile。
- 不新增数据库服务、容器、Redis、队列、后台线程，不改 Docker。
- 不删除旧 DeerFlow 路由、provider、channel、skill、测试或依赖；Phase 5 才做删除。
- 不重写 chat streaming、artifact viewer、auth、scheduler 或 LangGraph runtime。
- 不在前端实现 SQL policy、授权、risk、cost、hash/digest；只显示服务端安全字段。
- 不显示 chain-of-thought，不把 tool args 中 SQL 或结果 rows 放入轨迹。
- 不让 Harness import `app.*`，不为 Analytics 增加 Harness 专属条件分支。
- 不把报告 artifact 变成公共 URL，不保存原始 SQL、结果、prompt、token、credential 或 DSN。

必要文件若不在计划允许区域，先判断是否是同义且不可避免的测试/导出/guide 同步：可以最小扩展并在
报告“偏差”中逐文件解释；涉及新依赖、新服务、通用 Harness 行为、auth 或数据契约改变时必须停止。

## 4. TDD 与实现要求

- 每个任务保留首次 RED 与最终 GREEN 命令、退出码和关键输出。
- 后端 uv 命令一律 `--locked`；防止本地镜像导致 lock 漂移。
- 前端新增用户文案必须进入 `zh-CN`/`en-US`；代码注释/docstring/复杂测试说明中文优先。
- API 使用既有认证 fetcher；写请求继承 CSRF；Zod 严格解析外部 JSON。
- 管理员 UI 只是体验门禁，服务器认证/authorization 始终是安全边界。
- 生产文件硬上限 42；超过即停止报告，不得通过堆大文件或删除测试规避预算。

## 5. 必须提交的文档

- 本提示词原样提交；
- Phase 4 architecture 与 implementation plan 原样提交；
- 更新 `frontend/AGENTS.md` 和相关 Analytics guide；
- 更新 `docs/PROGRESS.md`，但在 GPT 复验前 Phase 4 必须仍是 `In progress`；
- `.reviews/phase-04-implementation-report.md` 必须忽略且不得提交。

## 6. 最终报告格式

按以下顺序一次性报告，避免分轮询问：

1. commit/parent/message、文件和生产文件预算；
2. 可行性四项证据；
3. 报告表/迁移/幂等发布/principal 隔离与敏感字段证明；
4. Lead/subagent 实际工具 schema 证明；
5. 前端 API/schema/query key/CSRF/管理员边界；
6. 数据源、指标、历史、报告、分析轨迹、响应式与可访问性证据；
7. 品牌扫描：允许保留与用户 UI 零残留分别列出；
8. RED/GREEN、后端/前端/Playwright/build 门禁命令、退出码与计数；
9. lock、Docker、固定 tag/tree、工作树状态；
10. 偏差（没有则写 `None`）；
11. `docs/PROGRESS.md` 状态，明确 Phase 5 未启动。

不要求重跑与本阶段无关的全部上游测试；门禁范围按计划 Task 8。任何测试失败不得描述为 PASS。
