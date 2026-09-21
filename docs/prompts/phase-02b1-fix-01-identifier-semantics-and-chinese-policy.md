# Phase 2B1 Fix 01：标识符语义与中文优先规范

你现在执行 InsightFlow Phase 2B1 Fix 01。该修复设计已由 GPT 和用户批准。

## 1. 仓库与起点

仓库：`D:\develop\workspace\InsightFlow`

开始执行前必须确认：

- `HEAD = 44f62c352fa82f473cd9b2b8e3b2ace62a2d82e6`；
- 本提示词文件
  `docs/prompts/phase-02b1-fix-01-identifier-semantics-and-chinese-policy.md`
  是唯一允许存在的未提交变更，由 GPT 预先写入，不得改写或删除；
- 除上述提示词文件外，工作树必须干净；
- 固定基线 tag 为 `upstream-v2.1.0-rc0`；
- 固定基线 commit 为 `609bfde0ced76ff0a58c02ff5c741df768f44502`；
- 固定基线 tree 为 `2473c22e163a3879490848a7995eb2b7be7f6f50`；
- `backend/uv.lock` 不得修改；
- Phase 2B2 不得启动。

本次交付两个彼此独立的提交，顺序不可颠倒。

## 2. 提交一：固化中文优先协作规范

提交信息：

```text
docs: establish Chinese-first project conventions
```

只允许修改或提交：

- `AGENTS.md`；
- `backend/app/analytics/AGENTS.md`；
- `frontend/AGENTS.md`；
- 本提示词文件。

不得修改 `CLAUDE.md`。

在仓库级和对应模块指南中加入简洁且不重复的语言规范：

1. InsightFlow 自有的新增或修改内容以中文为主要学习语言，包括：
   - 代码注释；
   - docstring；
   - 架构说明；
   - 实施计划；
   - AI 实施提示词；
   - 复杂测试场景说明。
2. 以下内容继续使用英文，不进行机械汉化：
   - 变量、函数、类和模块名；
   - API 字段、数据库字段和配置键；
   - 错误码、协议值、CLI 命令；
   - SQL 关键字；
   - 第三方库及行业标准术语。
3. 注释只解释以下内容：
   - 为什么这样设计；
   - 安全边界；
   - 非显然的算法或兼容行为；
   - 容易误改的约束。
4. 不允许给显而易见的代码逐行添加翻译式注释。
5. 不批量翻译未修改的 DeerFlow 上游文件。旧代码在后续真实修改时逐步本地化，避免产生巨大且难审查的纯翻译 diff。
6. 前端规范：
   - 新增用户可见文案必须进入现有 i18n 体系；
   - 至少同时提供 `zh-CN` 和 `en-US`；
   - 中文文案作为 InsightFlow 新页面的主要写作基准；
   - 保留中英切换；
   - 禁止在 JSX/TSX 中直接硬编码两套语言；
   - 本次只建立规范，不修改默认语言和现有页面。
7. 稳定错误码、机器日志字段和测试函数标识符可以保持英文；面向用户显示时通过 i18n 翻译。

本提交必须包含 GPT 预先写入的本提示词文件。提交后确认：

- guidance registry 不需要新增路径，因为没有增加新的 `AGENTS.md`；
- `git diff --check` 通过；
- 工作树恢复干净。

## 3. 提交二：修复标识符大小写与引号语义

提交信息：

```text
fix: preserve identifier semantics in semantic authorization
```

### 3.1 问题事实

当前 `_SchemaIndex`、`_PolicyIndex` 和 SQLGlot schema mapping 对物理标识符使用了过度 `casefold` 或自动归一化。

已经独立复现：当 PostgreSQL `SchemaSnapshot` 中真实表名为区分大小写的 `Orders` 时：

- `SELECT id FROM "Orders"` 被错误拒绝；
- `SELECT id FROM orders` 或 `SELECT id FROM "orders"` 可能被错误授权，并记录成 `public.Orders`。

这会使授权血缘指向与数据库实际执行对象不同的关系，必须在 Phase 2B2 前关闭。

### 3.2 允许修改范围

- `backend/app/analytics/infrastructure/semantic_authorizer.py`；
- `backend/tests/test_semantic_authorizer.py`；
- 必要时：
  - `backend/tests/test_query_authorization_domain.py`；
  - `backend/app/analytics/domain/schema.py`；
- `backend/app/analytics/AGENTS.md`；
- `docs/architecture/phase-02b1-semantic-authorization-core.md`；
- `docs/PROGRESS.md`。

除非失败测试证明必要，不要修改 domain 公共契约。不要提前增加 MySQL server 配置字段。

### 3.3 测试先行

先增加失败测试并实际运行，确认至少一个测试在旧实现上出现“错误授权”，而不是只出现测试构造错误。

将 RED 阶段命令与关键输出记录到：

```text
.reviews/phase-02b1-fix-01-report.md
```

该文件保持 gitignored，不提交。

### 3.4 SQLGlot schema 保留真实名称

在 `infrastructure` 内使用 SQLGlot `MappingSchema`，并明确设置：

- 正确 dialect；
- `normalize=False`。

不能再把普通嵌套 `dict` 交给 SQLGlot 后任其自动折叠真实元数据名称。

### 3.5 先按方言规范化 AST，再进行关系预检

预检关系存在性之前，先通过 SQLGlot 的方言标识符规范化处理 AST 副本。

PostgreSQL 必须满足：

- 未加引号的 `ORDERS`、`Orders`、`orders` 都按 PostgreSQL 规则折叠为 `orders`；
- `"orders"` 精确匹配小写真实对象；
- `"Orders"` 只精确匹配真实名称为 `Orders` 的对象；
- `"ORDERS"` 只精确匹配真实名称为 `ORDERS` 的对象；
- 不存在精确对象时必须拒绝。

不得自行用全局 `casefold()` 模拟 PostgreSQL 标识符规则。

### 3.6 物理对象与授权策略使用一致语义

以下标识符必须依据方言规范化后的 AST 与 `SchemaSnapshot` 中的真实名称进行精确匹配：

- catalog；
- schema；
- relation；
- column。

`PrincipalAccessPolicy` 中的 relation/column 规则必须精确对应解析到的真实 `SchemaSnapshot` 对象。禁止大小写不同的策略规则意外授权另一个真实对象。

只有 SQL 函数 allowlist 继续大小写不敏感；不要改变函数现有的 `casefold` 行为。

### 3.7 血缘输出保留真实数据库名称

`AuthorizedQuerySpec.relations` 和 `.columns` 必须记录 `SchemaSnapshot` 中的真实名称，而不是查询文本中的错误大小写，也不能全部强制小写。

### 3.8 MySQL 当前策略

本阶段没有真实服务器的 `lower_case_table_names` 信息，因此：

- 元数据与查询大小写精确匹配时可以通过；
- 无法确认的大小写不一致必须安全拒绝；
- 不得猜测服务器操作系统或 `lower_case_table_names`；
- 不得在本修复中引入连接、驱动或服务器探测；
- 在 analytics `AGENTS.md` 和架构文档中记录：Phase 2B2 的 MySQL schema adapter 必须读取或显式配置该服务器语义，再决定是否扩展 `SchemaSnapshot` 契约。

这是允许产生少量“误拒绝”的安全策略，不能产生“误授权”。

### 3.9 保留现有安全属性

不得削弱：

- Phase 2A 重新校验和 `PreparedQuery` 精确相等；
- relation、column、function 默认拒绝；
- `UNKNOWN_RELATION` 预检；
- correlated subquery 拒绝；
- HIGH 永远不允许；
- `schema_version` / `policy_version`；
- `PreparedQuery` 和 `AuthorizedQuerySpec` 无执行权限；
- SQLGlot 仅存在于 `infrastructure`。

### 3.10 中文规范

本次新增或修改的注释、docstring、测试场景说明采用中文。变量名、测试函数名、错误码以及第三方 API 名保持英文。不要为了本次修复批量翻译未触及文件。

## 4. 必须覆盖的测试矩阵

PostgreSQL 至少覆盖：

1. snapshot 同时包含 `orders` 和 `Orders`，两者使用可区分的列或策略；
2. 未加引号的 `orders` 授权到小写对象；
3. 未加引号的 `ORDERS` 仍按 PostgreSQL 规则授权到小写对象；
4. `"orders"` 只授权到小写对象；
5. `"Orders"` 只授权到混合大小写对象；
6. `"ORDERS"` 在没有同名真实对象时拒绝；
7. 混合大小写列：
   - 未加引号列按 PostgreSQL 规则折叠；
   - 引号列精确匹配；
   - 引号大小写错误时拒绝；
8. 大小写不匹配的 relation policy 不能授权；
9. 大小写不匹配的 column policy 不能授权；
10. 授权结果中的 relation/column inventory 保留 `SchemaSnapshot` 的真实大小写；
11. 普通全小写 schema 的现有查询保持通过。

MySQL 至少覆盖：

12. 元数据与查询大小写完全一致时通过；
13. 当前没有服务器 case-mode 证据时，大小写不一致安全拒绝；
14. 现有 MySQL 正常测试不回归。

回归测试必须继续覆盖：

- forged `PreparedQuery`；
- CTE；
- 非相关子查询；
- 相关子查询拒绝；
- 未知关系和列；
- 默认拒绝函数；
- sensitive/PII；
- cross-schema；
- Cartesian join；
- HIGH 不允许；
- 无 `plan_id` / `execute`。

## 5. 验证命令

所有 `uv` 命令必须带 `--locked`，并设置官方索引，避免用户级镜像改写锁文件。

在 `backend` 目录运行：

```powershell
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'

uv run --locked pytest `
  tests/test_semantic_authorizer.py `
  tests/test_authorize_prepared_query.py `
  tests/test_query_authorization_domain.py `
  tests/test_query_policy_domain.py `
  tests/test_sql_policy.py `
  tests/test_analytics_domain.py `
  tests/test_analytics_boundaries.py `
  tests/test_harness_boundary.py `
  tests/test_agent_guidance_check.py -q

uv run --locked ruff check `
  app/analytics `
  tests/test_semantic_authorizer.py `
  tests/test_authorize_prepared_query.py `
  tests/test_query_authorization_domain.py `
  tests/test_query_policy_domain.py `
  tests/test_sql_policy.py `
  tests/test_analytics_boundaries.py

uv run --locked ruff format --check `
  app/analytics `
  tests/test_semantic_authorizer.py `
  tests/test_authorize_prepared_query.py `
  tests/test_query_authorization_domain.py
```

不要运行无关前端全量测试，也不要启动 Docker；本修复仍为离线语义授权。

## 6. 最终边界检查

确认并在报告中记录：

- 最终产生两个提交，并给出两个完整 commit hash；
- 第一个提交只包含三个 `AGENTS.md` 和本提示词文件；
- 第二个提交只包含允许文件；
- `git diff --check` 通过；
- `backend/uv.lock` 相对 `44f62c3` 无变化；
- 固定 tag commit/tree 无变化；
- `.reviews/` 与 `text.md` 未提交；
- 工作树干净；
- Phase 2B2 未启动；
- `docs/PROGRESS.md` 保持 Phase 2B1 为待 GPT 复验状态，不能自行标记最终验收通过。

如果 SQLGlot 30.18.0 的实际行为与上述方案冲突，停止并报告最小复现，不得通过放宽匹配或大小写不敏感兜底绕过。

## 7. 完成回复格式

完成后用中文回复：

1. 两个提交的完整 hash；
2. RED 测试证明；
3. GREEN 测试数量与命令；
4. 标识符匹配的最终规则；
5. 所有偏差；
6. 工作树、锁文件和固定 tag/tree 状态。
