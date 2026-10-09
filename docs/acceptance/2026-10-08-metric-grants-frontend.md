# 指标显式授权前端接线验收

## 范围

本切片把已冻结的指标授权接口接入 Analytics 前端：严格解析授权列表与变更回执，使用同源 Analytics fetcher 发起无请求体的授予/撤销操作，并按指标缓存授权列表。成功后只刷新对应指标授权列表与普通指标目录。

管理员可从指标管理表格打开独立授权对话框，查看已授权 principal ID、授予新 ID 或逐项撤销。对话框明确说明草稿可预授权、启用后才会出现在受权用户目录中，以及数据源查询仍由独立策略授权。输入只接受 1–64 个字符且不含首尾空白或控制字符；页面不搜索、创建或补造账号资料。服务器 403 显示为禁止访问。

普通账号仍只使用普通指标目录，不渲染管理授权入口，也不会读取管理授权列表。指标授权只开放定义，不隐含数据源访问权限。

## 验证

- 旧 Agent 报告：首轮六文件 Rstest 为 96/99，三个失败来自测试夹具；`tsc --noEmit`、Prettier 与 diff 检查通过。原始日志未保存在当前工作区，未记录的命令不作推测。
- 旧 Agent 报告：ESLint 仅新授权面板测试有一条 `import/order`；本轮调整导入顺序后，两个目标测试文件 ESLint 通过。
- 本轮定点 Rstest：在 `frontend/` 执行 `python ../scripts/pnpm.py exec rstest run tests/unit/components/analytics/metric-grant-panel.dom.test.tsx tests/unit/components/analytics/analytics-admin-panels.dom.test.tsx -t "shows the current metric|retries a failed grant-list read|blocks duplicate submissions in the same turn|按指标打开独立授权面板"`，4 项通过、19 项按名称过滤跳过、0 项失败。
- 本轮在 `frontend/` 对两个目标测试文件运行 `python ../scripts/pnpm.py exec prettier --write tests/unit/components/analytics/metric-grant-panel.dom.test.tsx tests/unit/components/analytics/analytics-admin-panels.dom.test.tsx`，文件内容未变化；运行 `python ../scripts/pnpm.py exec prettier --check tests/unit/components/analytics/metric-grant-panel.dom.test.tsx tests/unit/components/analytics/analytics-admin-panels.dom.test.tsx ../docs/acceptance/2026-10-08-metric-grants-frontend.md`，通过。
- 本轮在 `frontend/` 运行 `python ../scripts/pnpm.py exec eslint tests/unit/components/analytics/metric-grant-panel.dom.test.tsx tests/unit/components/analytics/analytics-admin-panels.dom.test.tsx`，通过。`git diff --check` 和新增测试/文档的 `git diff --no-index --check` 未报告空白错误；no-index 因检测到新增文件差异返回预期状态码 1。

## 限制

未部署、未修改真实账号权限或演示数据；没有进行真实账号浏览器验收。该切片不代表后续 V3 部署验收或完整 15 场景通过。
