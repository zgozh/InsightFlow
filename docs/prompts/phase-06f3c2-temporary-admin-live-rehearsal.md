# Phase 6F3C2：临时管理员真实登录与 Reviewer 闭环彩排

你是 InsightFlow 的执行调查员。用户已明确授权：在 `insightflow-analytics-demo` **隔离演示项目**中建立临时管理员身份，进行真实登录和彩排，结束后清理本次新建的管理员账号；用户要求继续推进，只有其明确说“暂停”才暂停整体任务。起点应为 Reviewer 字段修复 `be7516e`，工作树干净。先读 `docs/acceptance/phase-06f1-real-analysis-rehearsal.md`、`docs/prompts/phase-06f3c-real-reviewer-probe.md` 和 `.reviews/phase-06f3c-fix-01-deepseek-reviewer-token-field.md` 的有关部分；不重跑已通过的 Reviewer 直连。

## 目标和授权边界

在现有合成 PostgreSQL 数据与隔离 Compose project 中，完成**最多一次**经 NGINX 的真实 Gateway analysis run：临时 admin 通过真实登录取得自己的会话，服务端建持久 analysis thread；Lead 用 `deepseek-flash` 调用受控目录和查询，形成同 run evidence，内部 Reviewer 审核后才发布 Markdown 报告；同 owner artifact GET 200、异 owner/线程读取保持拒绝，前端/API 安全轨迹可看到 Reviewer 稳定状态。记录每个阶段是否发生，若某一步失败，停在首个失败点，不靠反复模型调用凑通过。

这是 V3 的**一条真实集成彩排**，不是全量 pytest、E2E、AS-01..15 或发布验收。既有 Reviewer 定点测试与一次直连 HTTP 200 证据继续有效，不重复跑。不得修改生产代码、测试、配置模板、依赖或 lockfile；若彩排揭示产品缺陷，单独报告并等 GPT 规划修复。

## 先做零副作用可行性核对

1. 仅检查当前隔离 project 的资源、health、已有合成数据源/权限结构和应用认证/用户存储的**相关入口**。确认如何按仓库既有账号哈希与 role 约束创建一个唯一临时 admin，如何授予它**仅该合成 datasource** 的精确 active policy，以及如何在结束后精确撤销 policy、会话和本次账号。不得读取、重置、删除或覆盖 6F1 原管理员及其 policy/数据；不得使用 auth-disabled、伪造 JWT、直接注入 request.state.user 等方式代替真实登录。
2. 在任何写入前，先明确列出本次会创建哪些持久对象、各自唯一 ID/命名空间与归属、逐对象清理办法和验证办法。如果无法保证只清理本次创建的对象，停在变更前报告最小阻塞，不要先创建账号再猜如何删除。
3. 不启动/清理其他 Docker project，不执行 `down -v`、prune、整卷删除或批量删除。原有两个演示卷、原账号、既有线程/报告/审计均保留。若必须触及它们才能继续，停下报告。

## 执行与清理

- 优先使用现有应用认证服务/仓库接口创建临时 admin；如只存在受信的测试种子接口，可仅在隔离应用数据库中按其真实密码哈希/role 规则精确种入账号，并如实注明账号建立方式。**实际登录、线程创建、run、artifact 读取必须经过 NGINX/Gateway 公共路径**，不得绕过认证/准入。owner 身份不能自动替代数据源 policy，临时 policy 只给该账号及该合成 datasource，不能用 wildcard 或关闭策略。
- 临时口令在运行时生成并仅驻留进程内存；不得写聊天、命令行参数、shell 历史、日志、报告、仓库文件或可提交配置。若现有调用方式确实需要短期私有文件，只能放 Git 忽略目录、收紧权限，并在 `finally` 中按验证后的精确路径删除；不得留长寿命 bearer token/cookie。
- 最多一次模型驱动 Gateway analysis run。允许不消耗模型请求的 health/登录/权限预检，但不要为测试方便创建多条测试 run。若模型、Reviewer、writer 或 owner GET 失败，记录稳定代码/HTTP 状态和安全计数，不泄露自由文本、SQL、结果行、凭据、token、DSN 或报告正文，不现场改生产代码。
- 使用 `try/finally` 风格保证即使彩排失败也撤销临时 policy、会话/凭据并删除**本次临时 admin**；仅在验证 ID/owner 精确匹配后进行删除。对本次额外产生的 thread/report/artifact/audit，按现有合法清理契约处理；若不宜删除或没有安全清理路径，逐项报告残留及其不可访问性，绝不把“账号删除”写成“所有数据清空”。清理后读回证明临时账号与 policy 不存在，原 admin/合成 datasource/原有卷仍在；不把账号清理失败隐瞒为彩排成功。

## 交付和停线

将零副作用前置判断、真实认证方式、模型请求/run 次数、各阶段安全结果、精确清理读回、Docker 资源状态和未验证事项写入忽略的 `.reviews/phase-06f3c2-temporary-admin-rehearsal.md`。本阶段没有实现提交；已提交的本提示词是唯一文档变更。Gateway 彩排或清理出现意外时，先保护已有数据并如实报告；不可扩大到重置原管理员或删除演示卷。完成后交回 GPT 复验，并停在此切片，由 GPT 规划下一步。
