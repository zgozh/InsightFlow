# 目录条目到新建分析的操作衔接（2026-10-09）

## 行为

- 数据源目录每行提供“使用此数据源分析”，指标目录每行提供“分析此指标”；管理员目录保留原有管理操作，普通用户仍只看到目录操作。
- 操作进入 `/workspace/analysis/new`，把资源名称或指标 key 与名称组成自然语言问题，作为输入草稿预填。草稿最多 512 个字符，可继续编辑；不会自动提交或启动模型运行。
- 只有新建受控分析读取 `prompt` 查询参数。普通聊天与已有分析线程不消费该参数。目录名称只是用户目标文本，最终数据源和指标授权仍由服务端目录与策略校验。
- 空目录状态及其管理提示保持原样。未增加后端接口、服务端授权键或选择器框架。

## 定点检查

- `python ..\scripts\pnpm.py exec prettier --write ...`：对本切片受影响的前端实现与测试文件做定点格式化。
- `python ..\scripts\pnpm.py exec rstest run tests/unit/core/analytics/analysis-prefill.test.ts tests/unit/components/analytics/analytics-catalog-views.dom.test.tsx tests/unit/components/workspace/input-box-empty-skills.dom.test.tsx tests/unit/core/i18n/translations.test.ts`：4 个测试文件，26 项通过。
- `python ..\scripts\pnpm.py typecheck`：通过。
- `python ..\scripts\pnpm.py exec eslint <本切片受影响的 10 个 TS/TSX 文件>`：通过。

未构建、部署或发起模型请求；未修改后端/API 契约、README、发布配置或其它验收记录。
