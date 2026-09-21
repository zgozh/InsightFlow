# Phase 2B2 Fix 01：校准 MySQL 超时语义与验收镜像基线

你现在执行 InsightFlow Phase 2B2 Fix 01。该修复方案已经由 GPT 和用户批准。

## 1. 仓库、起点与目标

仓库：`D:\develop\workspace\InsightFlow`

开始执行前必须确认：

- `HEAD = 3a65865051731885064d721899e9a510c194f019`；
- 本提示词文件
  `docs/prompts/phase-02b2-fix-01-mysql-timeout-and-test-baseline.md`
  是唯一允许存在的未提交变更，由 GPT 预先写入，不得改写或删除；
- 除上述提示词文件外，工作树必须干净；
- 固定基线 tag 为 `upstream-v2.1.0-rc0`；
- 固定基线 commit 为 `609bfde0ced76ff0a58c02ff5c741df768f44502`；
- 固定基线 tree 为 `2473c22e163a3879490848a7995eb2b7be7f6f50`；
- `backend/uv.lock` 不得修改；
- Phase 2C 不得启动。

本次只修正已经确认的事实表述和验收环境契约，不重构生产执行逻辑，不增加 `KILL QUERY`
看门狗，也不重新设计错误码。

## 2. GPT 验收裁决

以下裁决已经确定，不再作为开放问题：

1. 接受 MySQL 8.4 流式生产路径使用“客户端 `asyncio.timeout()` + 销毁连接”终止查询；
2. 不增加独立连接上的 `KILL QUERY` 看门狗；
3. `MAX_EXECUTION_TIME` 继续设置，作为缓冲读取、`EXPLAIN` 以及未来驱动/数据库版本可能支持的纵深防御，
   但不得再声称它会终止当前 `connection.stream()` 服务端游标路径；
4. PostgreSQL 的服务端 `statement_timeout` + 客户端总时限语义保持不变；
5. Compose 验收环境必须使用字面量 `mysql:8.4`，不得允许环境变量切换 MySQL 版本；
6. `PLAN_STORE_UNAVAILABLE`、同步/异步 secret resolver、TLS 系统信任根叠加、标准库边界扩展、
   Gateway 异常映射和测试夹具参数绑定等偏差均已认可；
7. 列数超限继续映射 `UNSUPPORTED_RESULT_TYPE`，不新增决定码。文档需说明该码同时覆盖不支持的结果值类型、
   结果元数据和无法安全承载的结果形状；`RESULT_LIMIT_REACHED` 仍只用于携带截断结果的正常执行决定。

## 3. 单提交与允许范围

只允许产生一个提交：

```text
fix: align mysql timeout semantics and test baseline
```

只允许修改或新增：

- `backend/app/analytics/AGENTS.md`；
- `backend/tests/test_analytics_mysql_integration.py`；
- `backend/tests/test_analytics_database_harness.py`（新增，用于锁定专用 Compose 契约）；
- `docker/docker-compose.analytics-test.yml`；
- `docs/architecture/phase-02b2-governed-datasource-execution.md`；
- `docs/PROGRESS.md`；
- 本提示词文件。

禁止修改：

- `backend/app/analytics/**/*.py` 中除 `AGENTS.md` 外的任何生产代码；
- 既有领域决定码和公共契约；
- `backend/pyproject.toml`、`backend/uv.lock`；
- Phase 2B2 原始实施提示词和实施计划；
- Phase 2C 任何文件。

`.reviews/phase-02b2-fix-01-report.md` 可用于记录本地证据，但必须保持 gitignored，不得提交。

## 4. 修正 MySQL 超时语义文档

在 `backend/app/analytics/AGENTS.md` 和架构文档中准确区分以下路径。

### 4.1 PostgreSQL

- 只读事务内设置本地 `statement_timeout`；
- 服务端 timeout 负责中止查询；
- `asyncio.timeout(statement_timeout_ms + cancellation_grace_ms)` 限制客户端总耗时；
- 超时或取消后销毁连接，不得复用。

### 4.2 MySQL 8.4 + asyncmy 0.2.15

- 当前连接仍设置 `MAX_EXECUTION_TIME`；
- 缓冲 `exec_driver_sql` 路径会得到 MySQL errno 3024，因而能够证明服务端限制已武装；
- `EXPLAIN` 使用缓冲路径，继续受服务端限制保护；
- 生产查询使用 `connection.stream()` 服务端游标。真实 MySQL 8.4.11 实测中，
  `MAX_EXECUTION_TIME` 不会抢占该流式路径；
- 该流式路径的实际终止边界是 Gateway 外层
  `asyncio.timeout(statement_timeout_ms + cancellation_grace_ms)`，随后必须使连接失效并销毁；
- 真实数据库验收已经证明客户端超时返回后 `information_schema.processlist` 中残留活动查询为零；
- 服务端 `MAX_EXECUTION_TIME` 在流式路径中保留为纵深防御，但不能把尚未发生的服务端抢占写成保证。

不得把上述差异泛化成“取消所有服务端超时”。不得削弱现有客户端总时限、连接失效、事务回滚或残留查询检查。

## 5. 修正错误测试注释

`backend/tests/test_analytics_mysql_integration.py` 中已有测试行为和断言保持不变，只修正与实测相矛盾的注释或
docstring，尤其不能继续声称流式查询“最终由 `MAX_EXECUTION_TIME` 终止”。

说明必须与现有证据一致：客户端超时触发后，流式连接被失效/销毁；测试最终只接受 processlist 残留为零。
不得为了文字修正改写真实数据库测试逻辑、放宽断言或增加 sleep。

## 6. 固定专用 Compose 的 MySQL 版本

将：

```yaml
image: mysql:${ANALYTICS_MYSQL_TAG:-8.4}
```

改为：

```yaml
image: mysql:8.4
```

同时删除解释临时版本覆盖点的过期注释。端口覆盖 `ANALYTICS_MYSQL_PORT` 不属于镜像版本漂移，必须保留。

不得改为 `latest`、`8`、`8.0` 或 digest；本阶段跨平台验收基线就是官方 `mysql:8.4` Linux 镜像。

## 7. 测试先行与契约测试

新增 `backend/tests/test_analytics_database_harness.py`，先在修改 Compose 前运行并确认 RED，再修改 Compose 得到
GREEN。至少断言：

1. `docker/docker-compose.analytics-test.yml` 可以作为 YAML 读取；
2. `services.mysql.image` 精确等于字符串 `mysql:8.4`；
3. 文件文本不含 `ANALYTICS_MYSQL_TAG`；
4. MySQL 发布端口仍显式绑定 `127.0.0.1`；
5. MySQL 命令仍包含 `--lower-case-table-names=0`。

测试必须使用标准库路径 API 与项目已有 YAML 依赖，不得通过启动 Docker、拉取镜像或访问网络完成断言。
复杂测试场景说明使用中文；测试函数名和协议值保持英文。

将 RED/GREEN 命令与关键输出记录到 `.reviews/phase-02b2-fix-01-report.md`。

## 8. 进度账本

`docs/PROGRESS.md` 继续保持 Phase 2 为 `In progress`，不得自行标记 Phase 2B2 或 Phase 2 已最终验收。
将 next gate 更新为 `Phase 2B2 Fix 01 GPT 复验`，并简洁记录本修复提交。

## 9. 精简验证门禁

本修复只改文档、测试契约和 Compose 镜像字面量。不要重跑 864 项后端套件，不要重跑 PostgreSQL/MySQL
真实数据库门禁，也不要重新拉取镜像。

在 `backend` 目录运行：

```powershell
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'

uv lock --check
uv run --locked pytest `
  tests/test_analytics_database_harness.py `
  tests/test_agent_guidance_check.py -q

uv run --locked ruff check tests/test_analytics_database_harness.py
uv run --locked ruff format --check tests/test_analytics_database_harness.py
```

在仓库根目录运行不启动容器的配置检查：

```powershell
docker compose -f docker/docker-compose.analytics-test.yml config --quiet
git diff --check
```

如果本机 Docker CLI 不可用，只将 `docker compose ... config --quiet` 记为环境阻塞；不得因此改用真实数据库全量
测试代替。其余门禁仍必须完成。

## 10. 最终边界检查

提交前后确认并在报告中记录：

- 最终只有一个新提交，并给出完整 commit hash；
- 提交内容只包含第 3 节允许的文件；
- 本提示词文件已包含在提交中，且内容未被改写；
- 生产 Python 实现相对 `3a65865051731885064d721899e9a510c194f019` 零变化；
- `backend/pyproject.toml` 与 `backend/uv.lock` 相对起点零变化；
- 固定 tag commit/tree 未变化；
- `.reviews/` 与 `text.md` 未提交；
- 工作树干净；
- Phase 2C 未启动。

若修复过程发现必须修改生产逻辑、领域契约或依赖，立即停止并报告最小证据，不得扩大本修复范围。

## 11. 完成回复格式

完成后用中文回复：

1. Fix 01 的完整 commit hash；
2. RED/GREEN 测试证据；
3. Compose 最终 MySQL 镜像值；
4. PostgreSQL 与 MySQL 流式超时语义的最终表述；
5. 所有偏差或环境阻塞；
6. 工作树、生产代码、锁文件和固定 tag/tree 状态。
