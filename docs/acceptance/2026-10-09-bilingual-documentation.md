# InsightFlow 双语项目文档收尾记录（2026-10-09）

## 结果与边界

根目录 `README.md` 现为默认中文项目说明，`README_en.md` 为英文对照。已删除原根目录日文、法文、俄文和单独中文 README；根 `AGENTS.md` 与 `docs/current-capabilities.md` 的对应链接已指向新入口。`LICENSE`、`UPSTREAM.md`、包名及机器配置字段均保留。

文档描述以仓库当前源码与有日期的验收记录为依据，产品介绍聚焦当前的数据治理边界与报告流程；代码来源集中通过许可证和来源链接说明。README 嵌入的是现存首页 SVG 资源，并明确它不是工作台截图；当前仓库没有可发布的登录后界面截图或演示视频，因此没有杜撰演示资源。

## 结构参考

- [ByteDance DeerFlow 官方仓库与 README](https://github.com/bytedance/deer-flow)：参考项目定位、用户流程、运行方式和许可证来源等信息层次。
- [LangChain Deep Agents 官方 monorepo README](https://github.com/langchain-ai/deepagents/blob/main/libs/README.md)：参考 monorepo 的模块职责、套件边界与逐模块深入入口。

只借鉴信息架构；没有复制这些项目的宣传文字，也没有把它们的能力写成 InsightFlow 的能力。产品事实来自本地代码、根目录 `AGENTS.md` 与下列 2026-10-09 验收记录。

## 2026-10-09 已完成证据

新验收入口 `127.0.0.1:29388` 与旧本地演示入口 `127.0.0.1:29384` 分离；29384 不是最新构建的发布入口。先前获准的 live run 执行了受控查询并得到 3 行，随后在 Data 阶段以 `numeric_validation_failed` 终止。最新重测时 Gateway `c5a7` 正在运行，受控 PostgreSQL 查询仍成功，但 Data 输出的 `label_domain` 校验连续拒绝两次，定点修复仍在进行。当前没有成功报告产物，因此没有报告浏览器验收，也没有被描述为正例报告通过。

离线探针用合成证据验证了数值 `3901.25` 及引用关系。安全诊断修复之后，`test_analytics_agent_roles.py` 共 22 项测试通过。这两项验证解析器和拒绝原因日志的合同，不代表 live 候选内容被重放，也不替代真实报告闭环。准确记录见[live 正例](2026-10-09-postgres-positive-analysis-live.md)、[失败诊断](2026-10-09-analysis-positive-failure-diagnosis.md)、[离线数据合同与 UI 入口审查](2026-10-09-data-contract-and-ui-entry-review.md)及[解析器安全诊断](2026-10-09-data-parser-safe-diagnostics.md)。

`c5a7` 的定点修复和复验仍由另一验收切片推进；后续结果由总体验收负责人单独审查和补充。本记录及两份 README 都不宣称 AS-01～AS-15、Phase 6 或整体发布已完成。

## 非本次所有权文档的清理候选

本切片只处理根 README、根 `AGENTS.md`、`docs/current-capabilities.md` 和本记录。对 `docs/` 顶层及当前产品指南做了有界检查，以下是需要后续维护者评估的具体候选；均不在本切片所有权内，未作修改或删除。

| 路径 | 实际过时处或保留理由 | 引用影响与建议 |
| --- | --- | --- |
| `docs/ARCHITECTURE.md` | 概览仍列出已移除的 Custom/Managed、IM、Projects/Documents/Trash 与 Browser 页面；同时保有拓扑和扩展信息 | 顶层页链接到 `docs/architecture/insightflow-overview.md`，未发现其作为当前 README 的入口；建议后续合并有效独有事实后再由所有者决定是否退役 |
| `docs/architecture/insightflow-overview.md` | 2026-10-07 角色段仍写“不创建五个专职分析 Agent”，状态段引用旧 `29384` 阶段 | README 和本页互相引用它；建议改为现有 Lead、SQL Analyst、Data、Writer、Reviewer 调用流程并补充 `c5a7` 最新状态，不删除 |
| `docs/LOCAL_TRIAL.md` | 同一指南包含“配置速览”和“最短试用步骤”两套入门内容，并混有带日期的 Phase 6D2/6F1 试用记录 | README、`Install.md`、`config.example.yaml` 均有入口。保留独有的 PostgreSQL 试用和凭据说明；后续可评估合并重复步骤或把历史试用记录归档 |
| `Install.md` | 安装说明与 README/`LOCAL_TRIAL.md` 有部分步骤重叠，但仍有依赖、配置、启动和源码开发细节 | 根 `AGENTS.md` 与 `CONTRIBUTING.md` 指向此页；保留为规范安装指南，后续可减少重复的新手步骤 |
| `docs/` 顶层未发现独立多语言安装指南 | 有界检查的当前产品指南中没有日文、法文、俄文安装手册；原语言 README 是产品介绍而非独立安装文档 | 不增加删除项。`CONTRIBUTING.md` 是开发贡献流程，不是安装指南，应继续保留 |

## V0 文档检查

本切片只做文档回读、Markdown 本地链接路径检查、根语言 README 引用检查、品牌/旧语言引用检查和 `git diff --check`。没有运行应用测试、构建或 E2E；没有修改生产代码、服务、部署配置、`docs/PROGRESS.md`、`docs/INTERRUPTION.md` 或其它历史验收记录；没有 commit 或 push。
