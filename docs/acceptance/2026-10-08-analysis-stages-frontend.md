# AS09 分析阶段面板前端切片

## 行为

分析会话在聊天页顶部展示本次 run 已报告的阶段摘要；普通聊天不启用阶段状态。面板按 stage 显示最近状态和合同允许的 duration、rows、bytes、risk、token usage、cached 与稳定 code。页面刷新时，前端从现有 runs API 选最近 run，并从持久 events 接口回填。

live 与回放都使用 analysis-stage v1 strict Zod schema。live event 必须匹配 SDK stream metadata 的 thread_id/run_id；回放记录必须匹配事件类型、category、空 content、请求 run_id 与可用的 record scope。record.seq 只推进 after_seq；metadata.seq 只用于 run 内排序与去重。状态按 run 隔离，保留最近 128 条；冲突 key 保留先接受的可信事件。回放请求最多 20 页或 2000 条原始 run events。

面板不读取原始工具 payload，不显示 SQL、结果行、provider 错误或 CoT。未提供的 token usage 保持未知；run 终态直接采用 runs API 的状态，不据此补造成功阶段。

## 验证范围

V2：本切片改动 live stream hook、Analytics schema 与持久事件读取。定点覆盖严格 schema/reducer、分页游标与请求上限、run/thread 隔离、阶段面板可访问性和中英文本；执行受影响文件的 ESLint、Prettier 检查及 TypeScript typecheck。不运行整仓单测、构建、容器或真实模型。

## 交付证据

前端实现位于 `frontend/src/core/analytics/{types.ts,schemas.ts,analysis-stages.ts,stage-events-api.ts,use-analysis-stages.ts}`、`frontend/src/core/threads/hooks.ts`、`frontend/src/components/analytics/analysis-stage-panel.tsx`、`frontend/src/components/workspace/chats/chat-page.tsx` 与 Analytics 中英文 locale。直接相关测试覆盖 strict schema/reducer、持久回放分页、stream metadata 绑定、run/thread 隔离、面板展示与无阶段状态的普通聊天；`frontend/AGENTS.md` 已补充阶段面板约束。

- 定点 Rstest：5 个测试文件、12 项通过，覆盖上述协议与界面行为。
- TypeScript `typecheck` 通过。
- 对受影响实现和测试文件执行 ESLint、Prettier 检查，通过；本验收记录的 Prettier 检查通过。
- `git diff --check` 通过。

这是前端实现切片的交付记录；后端 producer 冻结后的真实 SSE 与刷新回填集成验收尚未执行，不据此声称 AS09 已完成整体验收。

## 同线程旧 run 回调回归修复

根因是 `onCustomEvent` 与 `onRunSettled` 把同线程回调 metadata 当作当前 scope；线程 stream 的终态回调也会再次发布 metadata。新 run 开始后，迟到的旧 custom/finish 因而能切回旧 run。修复后只有可信 stream metadata 更新当前 scope；custom 仅在当前 run 匹配时写入，已知为旧 run 的终态回调会被忽略，线程 hook 不再用 error/finish metadata 重设 scope。thread 切换时清空 scope ref。

- RED 复现：`python ..\scripts\pnpm.py rstest run tests/unit/core/analytics/use-analysis-stages.dom.test.tsx`，新增回归用例失败（2 项通过、1 项失败）；新 run 状态为 `running` 后收到旧 custom，状态被回退为空。
- 最终定点测试：`python ..\scripts\pnpm.py rstest run tests/unit/core/analytics/use-analysis-stages.dom.test.tsx tests/unit/core/threads/stream-options.test.ts`，2 个文件、5 项通过。
- 受影响 hook 与测试文件 ESLint、Prettier 检查及 `git diff --check` 均通过。
- shared thread hook 签名未改变，因此保留前一切片已通过的 typecheck 证据；本次未重跑全量检查。
