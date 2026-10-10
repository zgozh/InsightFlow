# CI E2E 定点修复验收记录

日期：2026-10-10

## 根因与修复

E2E run `38033361530` 的 job `114158680169` 报告 2 个失败和 1 个 flaky；失败记录见 `.reviews/ci-20261010/job-114158680169-failures.txt`。

- 分析轨迹用例的线程 fixture 缺少 `metadata.analysis_mode: true`。现有分析路由会先读取 `/api/langgraph/threads/{thread_id}` 的 metadata；mock 返回 200，但把该线程当作普通聊天并阻止挂载分析 UI，所以窄屏的 trace trigger 不存在。fixture 已为该分析线程提供正确 metadata。
- 挂载分析页面后，线程 runs fixture 给出一个 run，页面继续请求 `/api/threads/{thread_id}/runs/{run_id}/events?limit=100`。该 Gateway 路径未被 mock，Next 因此尝试代理到 `127.0.0.1:8001` 并收到 `ECONNREFUSED`，没有 HTTP 响应码。用例现在对精确 thread/run events 路径返回合法空列表 `200 []`，并检查该响应状态。
- 报告索引用例仍禁止所有 `/artifacts/` 链接，但当前列表提供通过 Gateway owner check 的下载路由 `/api/threads/{thread_id}/artifacts...`。断言已改为检查线程限定的下载路径、`download=true` 和下载属性，并继续检查回到分析页的链接。trace 用例仍断言 SQL、结果行内容不进入面板。
- goal 用例之前只观察到 PUT 请求已发出，没有等待保存响应。现先等待 `/api/threads/{thread_id}/goal` PUT，并断言状态为 200、响应含已保存目标，再检查 UI 状态与保存请求事件；没有增加用例 timeout 或 retry。

本次只改 `frontend/tests/e2e/insightflow-workspace.spec.ts` 和 `frontend/tests/e2e/chat.spec.ts`，没有改生产代码、通用 fixture、API schema 或报告 owner/evidence 契约。

## 定点验证

- 使用现有 Next 构建，先设置 `SKIP_ENV_VALIDATION=1`、`DEER_FLOW_AUTH_DISABLED=1` 并运行 `python scripts/pnpm.py exec next start --hostname 127.0.0.1 --port 3000`；随后设置 `PLAYWRIGHT_SKIP_WEB_SERVER=1`、`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000`，只运行三个失败/不稳定用例：

  `python scripts/pnpm.py exec playwright test tests/e2e/insightflow-workspace.spec.ts tests/e2e/chat.spec.ts --grep 'the analysis trace shows governed evidence and never the SQL|the report index links back into the analysis route|goal command saves the goal on a plain new chat'`

  结果：3 passed。补充 events mock 后 Next 服务退出日志中没有连接 8001 的失败。
- `python scripts/pnpm.py exec prettier --check tests/e2e/insightflow-workspace.spec.ts tests/e2e/chat.spec.ts`：通过。
- `python scripts/pnpm.py exec eslint tests/e2e/insightflow-workspace.spec.ts tests/e2e/chat.spec.ts`：通过。
- `git diff --check -- frontend/tests/e2e/insightflow-workspace.spec.ts frontend/tests/e2e/chat.spec.ts`：通过。

未运行完整 E2E、重放/API 套件或构建；本次未提交或推送。提交后的 Linux Actions 负责最终集成验证。
