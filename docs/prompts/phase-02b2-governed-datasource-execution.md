# Phase 2B2 执行提示词：受控数据源执行闭环

你现在实施 InsightFlow Phase 2B2。用户已明确选择单阶段方案 B，架构规格已经批准。

## 必读顺序

1. 根 `AGENTS.md`；
2. `backend/AGENTS.md`；
3. `backend/app/analytics/AGENTS.md`；
4. `docs/architecture/phase-02b2-governed-datasource-execution.md`；
5. `docs/superpowers/plans/2026-09-21-phase-02b2-governed-datasource-execution.md`；
6. 本提示词。

架构文档决定“做什么与为什么”，实施计划决定文件、接口、TDD 顺序和验收命令，本提示词只补充执行纪律。发生冲突时停止并报告，不得自行放宽安全条件。

## 起点

- repo：`D:\develop\workspace\InsightFlow`；
- `HEAD` 必须是 `07e5d952d4c14173941336ce70d2ca3d4af4741e`；
- 固定 tag `upstream-v2.1.0-rc0` 必须仍为 commit
  `609bfde0ced76ff0a58c02ff5c741df768f44502`、tree
  `2473c22e163a3879490848a7995eb2b7be7f6f50`；
- 允许存在的 architect-owned 未提交内容只有：
  - architecture 状态行修改；
  - 本 phase plan；
  - 本 prompt；
- 上述三份文档由 GPT 写入，不得删除、改写语义或拆出本阶段；最终与实现一起提交。

开始前把 `git status --short`、HEAD、tag commit/tree 和 `backend/uv.lock` SHA-256 写入忽略的实施报告。

## 执行纪律

1. 严格按计划 Task 1—9 顺序 TDD：先 RED、记录真实失败，再写最小实现、跑 GREEN。
2. 用户已选择一次性交付完整 2B2，因此最终只允许一个提交：

```text
feat: add governed datasource execution
```

3. 任务间不要创建 commit；使用 `.reviews/phase-02b2-implementation-report.md` 保存检查点和证据。
4. Docker 已安装，PostgreSQL 16/MySQL 8.4 真实集成门禁是必跑项，mock 不能替代。
5. 新增/修改的注释、docstring、复杂测试说明使用中文；变量、类型、错误码、协议字段和 SQL 保持英文。
6. 不追求注释数量，只解释安全原因、方言差异、状态机和清理约束。
7. 不启动 2C，不添加 API、Agent Tool、MCP、前端、ORM、业务 migration、Redis、消息队列或审批流程。

## 依赖纪律

只允许将规格确定的三个包声明为 backend 直接依赖：

```text
sqlalchemy[asyncio]>=2.0.49,<2.1
asyncpg>=0.31,<0.32
asyncmy>=0.2.14,<0.3
```

在改 lock 前后导出包坐标并比较。只允许新增 asyncmy 及其必需传递依赖、把已有 SQLAlchemy/asyncpg 提升为直接依赖，以及解析器为满足上述范围所必需的最小变化。出现任何无关升级/降级立即停止并报告。

锁更新完成后，所有 uv 命令必须使用：

```powershell
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv run --locked ...
```

## 关键审查红线

- `PreparedQuery`、`AuthorizedQuerySpec` 仍不可执行；只有被服务端 plan store 原子领取的 plan 能到数据库。
- 创建 plan 前、EXPLAIN 后、正式执行前必须完整重跑 Phase 2B1，并要求授权值精确相等。
- HIGH 永远不执行。
- plan token 使用 `secrets.token_urlsafe(32)`；store 只保存 SHA-256，不保存 raw token。
- 不存在、过期、重放、principal 不匹配对外统一为 `PLAN_UNAVAILABLE`。
- claim 必须是一个锁内原子操作，且在所有外部 I/O 前发生；后续失败不恢复 token。
- credential 只存在于 infrastructure 私有对象；不得进入 repr、日志、异常、domain 或 receipt。
- 不记录原始 SQL、DSN、用户名、密码、完整 plan token 或原始 EXPLAIN JSON。
- 每次数据库调用使用 `NullPool` 和新连接；timeout/cancel 后连接必须销毁。
- EXPLAIN 禁止 ANALYZE；执行 SQL只能精确取自 `authorized.prepared.sql`。
- PostgreSQL 和 MySQL 都必须建立数据库只读事务并有服务端+Python 双层 timeout。
- MySQL 必须读取 `@@lower_case_table_names`，只有 0 放行；1/2/缺失默认拒绝。
- 结果逐行消费，禁止 `fetchall()`；未知类型不得调用 `repr()`/`str()`。
- Docker compose 只能绑定 `127.0.0.1`，不得使用管理员账号作为被测查询账号。

## 允许修改范围

以实施计划 File map 为准，外加计划明确写出的现有 `__init__.py`、boundary test、compose bind test、AGENTS 和 PROGRESS。禁止修改：

- Harness 生产代码；
- Gateway/API；
- frontend；
- 默认 production/development compose；
- `CLAUDE.md`、README、LICENSE；
- Phase 2A/2B1 的历史 plan 和 prompt；
- 固定 tag。

如果确实需要 File map 之外的文件，先停止并只报告：所需路径、哪条验收标准要求它、为什么现有 seam 无法完成。未经 GPT 批准不得扩大范围。

## Docker 门禁

专用 compose 必须可重复启动和清理。编排脚本必须：

1. 校验 Docker/Compose；
2. 启动两种数据库并等待 health；
3. 只通过环境变量注入测试 secret；
4. 运行两个 integration 文件；
5. 失败时打印 compose ps 和有限尾部日志；
6. `finally` 中执行 down，不能留下容器或持久测试卷。

若 Docker 引擎不可用，先完成不依赖 Docker 的工作并保持未提交，然后报告准确阻塞；不得把 integration 标成 skip 后宣告完成。

## 最终门禁

完整执行实施计划 Task 9 的单元、回归、Ruff、format 与 Docker 命令。另确认：

- `git diff --check` 为 0；
- production/test 文件数没有超过规格预算；
- 依赖坐标无越界漂移；
- `.reviews/`、test secret、Docker 数据和 `text.md` 未提交；
- 固定 tag commit/tree 未变化；
- `docs/PROGRESS.md` 仍将 Phase 2 标为 In progress，next gate 是 `Phase 2B2 GPT 复验`；
- 工作树干净；
- 2C 未启动。

## 报告与停止条件

实施报告至少包含：

- 每项 Task 的 RED/GREEN 命令和关键输出；
- 单元/回归测试数量；
- PostgreSQL/MySQL 镜像、health、只读、EXPLAIN、timeout、cancel、配额实测证据；
- 依赖坐标 before/after；
- 安全红线逐项结果；
- changed paths、文件预算、commit/parent、tag/tree、lock hash；
- 所有偏差及其是否收紧或放宽安全性。

以下任一情况必须停止，保持未提交并报告，不得自行变更设计：

- 真实数据库行为与规格冲突；
- 无法证明查询已被服务器取消；
- MySQL 不是 `lower_case_table_names=0`；
- 依赖出现无关漂移；
- 需要放宽 Phase 2A/2B1；
- 需要 API、持久化或 File map 外架构改动；
- 任一凭证或原始数据库错误可能泄露。

完成后用中文回复：最终 commit hash、测试与 Docker 结果、依赖变化、偏差、工作树/tag/lock 状态，并明确写“Phase 2C 未启动”。
