# Phase 4 Fix 01：最终保留界面的品牌闭环与干净 diff

## 1. 复验结论

Phase 4 主提交 `ae8980558250e111616a3c2fa9c0b28f90c46485` 暂不通过，需一个独立小修复提交。

裁决如下：

- 接受主提交 42/42 的生产文件预算和三处结构性合并，不要求重新拆分或重构。
- 不接受把 `/login`、`/setup` 的 `DeerFlow` 产品标题留到 Phase 5；认证入口属于最终保留界面。
- 最终保留的 Workspace/设置/定时任务界面中仍直接面向用户的 DeerFlow 产品文案，本修复一并改为
  InsightFlow。
- 计划在 Phase 5 物理删除的 Channels、Custom Agent、Capability Center、Voice 等旧模块中的文案，
  本修复不批量翻译或改名。
- 默认 `git diff --check 7bd21d7..HEAD` 必须 exit 0；不得用
  `core.whitespace=-blank-at-eof` 绕过。

本修复允许触碰 4 个既有生产文件，作为复验纠错例外，不计入主提交 42 文件预算；不得新增生产文件。

## 2. 唯一允许的生产文件

- `frontend/src/app/(auth)/login/page.tsx`
- `frontend/src/app/(auth)/setup/page.tsx`
- `frontend/src/core/i18n/locales/zh-CN.ts`
- `frontend/src/core/i18n/locales/en-US.ts`

允许同步修改直接受影响的既有测试，以及：

- `docs/architecture/phase-04-insightflow-product-workspace.md`
- `docs/superpowers/plans/2026-09-22-phase-04-insightflow-product-workspace.md`
- `docs/prompts/phase-04-insightflow-product-workspace.md`
- `docs/PROGRESS.md`
- 本提示词（原样提交）。

禁止修改其他生产代码、依赖、lockfile、Docker、API、数据契约、迁移、工具、路由结构或 Phase 5
待删除模块。若确有直接受影响测试不在上述描述中，可以最小修改并在报告列明；不得扩大生产范围。

## 3. RED / GREEN 要求

先新增或调整测试，让以下事实在修改生产代码前失败：

1. `/login` 与 `/setup` 所有可达渲染分支的产品标题均为 `InsightFlow`。
2. 中英文的会话保持提示、主聊天输入免责声明、最终保留的定时任务状态/说明、键盘快捷键、设置页和
   Memory 说明使用 `InsightFlow`，不再使用 `DeerFlow`。
3. About 的上游归属仍明确包含 `DeerFlow v2.1.0-rc0`，不得为了品牌扫描删除开源来源。

只修改最终保留产品表面的 copy。以下内容可以保留并必须在扫描报告中分类：

- MIT LICENSE、README、About 上游归属；
- 内部类型、类名、协议字段、storage key、API 名称和代码注释；
- mock 对话正文、测试输入、外部集成返回文本等“用户/外部数据”，而非产品 chrome；
- Phase 5 明确将删除的旧模块及其专属 i18n 文案。

不得为了让扫描变成零而机械替换 `deerflow_*`、`DeerFlowClient`、storage key 或 attribution。

## 4. 文档 whitespace

三份 Phase 4 原始文档当前以两个 LF 结尾。只删除多余的最后一个空行，使每份文件恰好以一个 LF
结束；不得改写文档正文。随后默认执行：

```bash
git diff --check 7bd21d7721e3caf3cc7cc1b90bb9d3b51b7b2d8a..HEAD
```

必须 exit 0 且无输出。

## 5. 精简门禁

不重跑后端、数据库、Docker、448 项 focused backend、1756 项全量 frontend 或完整 build。只运行：

1. 直接受影响的 i18n/auth/unit tests；
2. `frontend/tests/e2e-auth/auth-setup-recovery.spec.ts`，以及一个覆盖主聊天免责声明的 focused E2E；
3. 对 4 个生产文件和受影响测试执行 ESLint/TypeScript/Prettier 的最小检查；若项目命令不能按文件
   精确运行，允许执行 `pnpm lint` 与 `pnpm typecheck`；
4. 用户可见品牌分类扫描；
5. 默认 `git diff --check 7bd21d7..HEAD`；
6. tag/tree、两个 lockfile、Docker、工作树状态检查。

若本机 Playwright 浏览器仍需要 junction，不重新下载；可以复用 Phase 4 已验证的真实浏览器环境，
但必须在报告中注明。

## 6. 提交与状态

- 恰好一个修复提交，建议 message：`fix: complete insightflow visible branding`。
- `docs/PROGRESS.md` 保持 Phase 4 `In progress`，next gate 改为 `Phase 4 Fix 01 GPT review`。
- Phase 5 不得启动。
- `.reviews/` 不提交，工作树最终干净。

## 7. 回报格式

一次性报告：

1. commit/parent/message 与精确文件集合；
2. RED/GREEN；
3. `/login`、`/setup` 各渲染分支与保留界面 copy 的最终品牌证明；
4. 品牌扫描分类，尤其证明 attribution 未删、Phase 5 残留未偷改；
5. 默认 `git diff --check` 的退出码与输出；
6. focused 门禁、tag/tree/lock/Docker/工作树；
7. 偏差（没有写 `None`）。
