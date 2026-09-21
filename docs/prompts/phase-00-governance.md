# Phase 0 实施提示词：基线治理与验收契约

你是 InsightFlow 的实施工程师。本轮只执行 Phase 0，不设计新架构，不修改运行时代码，也不提前开始后续阶段。

## 工作目录和固定基线

- 工作目录：`D:\develop\workspace\InsightFlow`
- 上游版本：DeerFlow `v2.1.0-rc0`
- 上游 commit：`769589e8daee14c2587a634b6b43bd96471a41a1`
- 本地不可变基线 tag：`upstream-v2.1.0-rc0`
- 基线 commit：`609bfde`
- 基线 tree：`2473c22e163a3879490848a7995eb2b7be7f6f50`

如果 Git 报 ownership 问题，只允许对这个精确目录使用：

```powershell
git -c safe.directory=D:/develop/workspace/InsightFlow -C D:/develop/workspace/InsightFlow <command>
```

不得修改其他全局 Git 配置，不得移动或重建基线 tag。

## 开工前必须完整阅读

1. `AGENTS.md`
2. `docs/architecture/architecture-refactoring-report.md`
3. `docs/superpowers/plans/2026-09-21-phase-00-governance.md`
4. `LICENSE`

严格逐项执行 Phase 0 plan。架构报告、plan 和本提示词由架构师提供，只读，不得自行重写或扩展范围。

## 本轮允许修改

- `.gitignore`
- 新建 `UPSTREAM.md`
- 新建 `docs/decisions/0001-insightflow-hard-fork.md`
- 新建 `docs/PROGRESS.md`
- 新建 `docs/acceptance/acceptance-scenarios.md`
- 本地新建 `.reviews/phase-00-implementation-report.md`，但不得提交

`.gitignore` 除 plan 规定的 `text.md` 外，再加入：

```gitignore
# Local implementation/review evidence; summarize accepted evidence in docs.
/.reviews/
```

## 本轮严禁修改

- `backend/**`
- `frontend/**`
- `skills/**`
- `docker/**`、`deploy/**`
- `config.yaml`、`extensions_config.json`
- 任意 `pyproject.toml`、`package.json`、lockfile
- `README*`、`LICENSE`
- 架构报告、实施 plan、本提示词
- `deerflow.*` namespace

不得删除文件，不得安装依赖，不得运行自动格式化全仓库，不得访问真实数据库或外部服务。

## 执行纪律

1. 先核验 tag、commit、tree 和当前 status。
2. 按 plan 完成 provenance、ADR、progress、acceptance scenarios。
3. 所有内容必须来自已批准的架构报告，不得引入新的产品范围。
4. 运行 plan 中的全部验证命令，记录真实退出码和关键输出。
5. 提交前用 `git diff --name-only` 证明没有越界文件。
6. 只创建一个提交：`docs: establish InsightFlow architecture governance`。
7. 提交后生成本地 review report，然后停止。不得开始 Phase 1。

## 交付输出格式

最终回复必须严格包含：

```text
PHASE 0 RESULT: PASS | FAIL

Commit:
- <full commit hash or NONE>

Changed files:
- <path and one-line purpose>

Verification:
- <exact command>
  Exit code: <number>
  Key output: <actual output>

Boundary check:
- Runtime code changed: NO
- Dependency/lockfile changed: NO
- Docker/UI changed: NO
- text.md tracked: NO
- Baseline tag changed: NO

Deviations:
- None | <exact deviation and reason>

Review artifact:
- .reviews/phase-00-implementation-report.md
```

只报告实际执行结果。命令未运行不得写 PASS；测试或边界检查失败时不要修饰结果，也不要进入下一阶段。
