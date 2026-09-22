# Phase 2C1 Fix 01 实施提示词：修正差异门禁与验证报告真实性

你是 InsightFlow Phase 2C1 的修复工程师。直接在当前 `main` 上完成一次严格限域的小修复；不得开始 Phase 2C2，不得修改任何生产代码、测试代码或架构规格。

## 1. 起点与已确认事实

- `HEAD` 必须是 `eda88786578379cff00aee803108ffe56d36d9c2`。
- parent 必须是 Phase 2C1 规格提交 `456b57a302b5fe95531a43b11361653a1a8e7d8f`。
- 固定 tag `upstream-v2.1.0-rc0` 必须保持 commit `609bfde0ced76ff0a58c02ff5c741df768f44502`、tree `2473c22e163a3879490848a7995eb2b7be7f6f50`。
- 开始时工作树只应存在本提示词这个未跟踪文件；如有其他变化，立即停止并报告。
- GPT 已独立运行以下聚焦门禁：

  ```text
  uv run --locked pytest \
    tests/test_analytics_sql_plan_store.py \
    tests/test_analytics_sql_audit_log.py \
    tests/test_analytics_persistence_migrations.py \
    tests/test_query_execution_use_cases.py -q
  -> 83 passed in 18.37s
  ```

- GPT 已稳定复现：

  ```text
  git diff --check 456b57a302b5fe95531a43b11361653a1a8e7d8f..eda88786578379cff00aee803108ffe56d36d9c2
  docs/superpowers/plans/2026-09-22-phase-02c1-durable-analytics-control-plane.md:353: new blank line at EOF.
  ```

因此 Phase 2C1 生产实现暂未发现功能缺陷，但当前提交不满足自己报告的 `git diff --check` 门禁，必须修正后才能验收。

## 2. 唯一修复内容

1. 删除 `docs/superpowers/plans/2026-09-22-phase-02c1-durable-analytics-control-plane.md` 文件末尾多余空白行，使文件以且仅以一个换行结束。
2. 原样提交本提示词 `docs/prompts/phase-02c1-fix-01-verification-integrity.md`，作为审查与修复轨迹。
3. 在忽略目录 `.reviews/` 中更正 Phase 2C1 实施报告：明确原提交的 `git diff --check` 结论有误、记录 GPT 的复现结果与 Fix 01 的修复后结果。该报告不得提交。

不得借机改写施工计划正文，也不得修改任何其他文件。

## 3. 允许修改集合

提交中必须恰好只有：

- `docs/superpowers/plans/2026-09-22-phase-02c1-durable-analytics-control-plane.md`
- `docs/prompts/phase-02c1-fix-01-verification-integrity.md`

允许更新但不得提交：

- `.reviews/phase-02c1-implementation-report.md`

任何其他文件变化都必须停止并报告，不能自行扩大范围。

## 4. 验证要求

本修复不改代码，不得重跑 839 项套件、Ruff 全目录或任何 Docker/真实数据库门禁。只运行并记录：

```bash
git diff --check eda88786578379cff00aee803108ffe56d36d9c2..HEAD
git diff --check 456b57a302b5fe95531a43b11361653a1a8e7d8f..HEAD
git diff --name-only eda88786578379cff00aee803108ffe56d36d9c2..HEAD
git status --short
git rev-parse upstream-v2.1.0-rc0
git rev-parse upstream-v2.1.0-rc0^{tree}
```

注意：提交前可对工作树运行 `git diff --check`；提交后必须运行上面两条带范围的命令。两者都必须 exit 0 且无输出。

## 5. 提交纪律

- 只创建一个提交：`fix: restore phase 2c1 verification integrity`
- commit parent 必须是 `eda88786578379cff00aee803108ffe56d36d9c2`。
- 完成后工作树必须干净，`.reviews/` 保持忽略。
- `docs/PROGRESS.md` 不修改；仍由 GPT 在复验通过后安排后续阶段。
- Phase 2C2 不得启动。

## 6. 最终回复格式

用中文简要报告：

1. commit hash、parent、message；
2. 两个已提交文件的精确列表；
3. 两条 `git diff --check` 的退出码与输出；
4. 固定 tag commit/tree、工作树状态；
5. 明确承认并更正原交付报告中 `git diff --check` 的误报；
6. 明确写“没有修改生产代码或测试，未重跑大套件与 Docker，Phase 2C2 未启动”。

不得自行宣告 Phase 2C1 最终验收通过，等待 GPT 复验。
