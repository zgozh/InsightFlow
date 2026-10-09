# 产品品牌切片独立审查修正

执行者 `gpt-6-luna` / max；只完成下述已确认修正，不重新设计文档/品牌/黑洞。主会话已独立回读当前README/架构/About/i18n/Footer/diff。LICENSE保持不改。所有已有diff保留。

## 确定检查证据与失败

主会话通过正确解释器明确运行：
- `python ../scripts/pnpm.py typecheck` 退出0；
- `python ../scripts/pnpm.py exec rstest run tests/unit/components/workspace/settings/about-content.test.ts tests/unit/core/i18n/insightflow-branding.test.ts` 9/9通过，实际stdout已见；
- Prettier定点失败，三个文件：`src/components/workspace/workspace-nav-menu.tsx`、`tests/unit/components/workspace/settings/about-content.test.ts`、`tests/unit/core/i18n/insightflow-branding.test.ts`。请只对这三文件prettier --write再check，无行为改变不重跑typecheck/单元。

以后宿主所有pnpm显式 `python ../scripts/pnpm.py ...`，不要直接调用 `.py` 文件的Windows关联，此前无stdout不能作为测试数量/执行证据。修报告记录：采用本节确定证据，不声称旧Playwright实际通过。

## 漏掉的产品入口

- `frontend/src/components/workspace/recent-chat-list.tsx` 的 handleShare 在localhost把链接发往 `https://deer-flow-v2.vercel.app`：删除旧demo fallback，始终使用 `window.location.origin` + 现有pathOfThread（本项目未配置公共分享服务，链接仍受owner身份）。这是确认的可见入口缺陷，使用现有share DOM测试新增或更新localhost origin行为保护，勿抽无用helper。
- `frontend/src/components/workspace/settings/memory-settings-page.tsx` 下载名 `deerflow-memory-` 改 `insightflow-memory-`；现有memory test如覆盖文件名仅更新，不新增机械测试。
- `frontend/src/core/sidecar/context.ts` 的side conversation prompt文本改InsightFlow，这是产品指代，不改内部key。
- `frontend/src/core/threads/static-demo.ts` 可见fixture产物文件名 research_deerflow 改当前项目主题，并核对匹配fixture定义；不把示例内容宣传为实时结果。
- 其余可见源中的旧品牌/原站点仅定点扫描。内部storage/metadata/errorcode/packageclass/历史注释不批量替换。
- 新 `docs/architecture/insightflow-overview.md` 的“指标服务提供指标口径”应精确为“当前指标目录列出已登记口径，尚无独立自然语言口径解析服务”，不把现状缺口写成已有MetricService。

## 交付验证

独占上述文件、相应现有测试、品牌acceptance/PROGRESS、当前公开文档相对链接checker（在忽略目录小Python脚本，UTF8，不写长shell one-liner）。不改AS01/15环境/报告，不部署旧栈。

针对share真实行为回归优先RED/GREEN，然后受影响ESLint/format、该share测试；涉及TS行为的修改才重跑typecheck。About/i18n已通过证据不重复。用既有本地Next若在运行，明确 `PLAYWRIGHT_SKIP_WEB_SERVER=1` + `PLAYWRIGHT_BASE_URL=http://localhost:3000` 跑landing两品牌case，并保存桌面/手机完整截图（品牌验收用新路径避免覆写黑洞原证据）。服务器缺失可用dev有界启动，无需登录/模型；`pnpm`用正确Python入口。文档链接checker忽略绝对URL、锚点和代码，报告真实缺链并只修本切片相关。

固定29384容器手动恢复的问题仍待用户回复；本轮先源码/本地review，不绕过之前主机拒绝，不等待部署才能交回。完成准确输出/截图后马上返回，不为了全面放心再跑其他suite。不要写新长报告，修原品牌报告足够。主会话正在准备AS15有界诊断，后续继续整体发布。
