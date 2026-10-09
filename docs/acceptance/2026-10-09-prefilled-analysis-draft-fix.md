# 显式预填分析草稿隔离

## 变更

- 仅当分析模式、新线程且存在目录预填时，`ChatPage` 使用当前生成的 `threadId` 作为草稿键。
- 普通聊天和无预填的新分析继续使用共享 `new` 键；历史分析继续使用原线程 ID。
- `useThreadChat` 在离开 `/new` 路径时清空新线程引用，重新进入时生成新 UUID。一次新分析内的重渲染保持同一 ID；`InputBox` 已有的 `hydratedDraftKey` 门闩继续保护用户编辑。
- DOM 回归覆盖数据源预填与编辑、离开后用新线程 ID 进入指标预填、编辑后同 ID 重渲染、以及旧 `new` 草稿仍可恢复。测试使用真实 `InputBox` 和 sessionStorage draft helper。

## 定点验证

- `python ..\scripts\pnpm.py rstest run tests/unit/components/workspace/input-box-empty-skills.dom.test.tsx`：通过，4 项测试。
- `python ..\scripts\pnpm.py exec eslint src/components/workspace/chats/chat-page.tsx tests/unit/components/workspace/input-box-empty-skills.dom.test.tsx`：通过。
- `python ..\scripts\pnpm.py exec tsc --noEmit --pretty false`：通过。
- `python ..\scripts\pnpm.py exec prettier --check src/components/workspace/chats/chat-page.tsx tests/unit/components/workspace/input-box-empty-skills.dom.test.tsx`：通过。

本切片未改动通用 `InputBox` 草稿管理、后端或其它页面；未构建、部署或调用模型。生产构建与真实目录双击浏览器探针留给主会话审查后执行。
