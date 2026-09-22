# Phase 5：能力收缩与仓库瘦身

## 1. 目标

Phase 5 把 InsightFlow 从通用 DeerFlow 平台收缩为个人可理解、可演示、可维护的企业经营分析 Agent。
删除标准不是“文件看起来没用”，而是：该能力不进入最终架构、Demo、简历叙事或安全主链，且已有明确
替代路径。

目标预算沿用 `docs/PROGRESS.md`：tracked files 850–1050，硬上限 1200；生产源码 450–650，
测试 250–350，有效文本 LOC 140k–220k。安全覆盖优先于数字；若审计证明目标与 KEEP 契约不可同时
满足，Phase 5A 必须给出按域计算的最低可达值和证据，不得删除安全测试凑数字。

Phase 5 不新增业务功能。功能缺口回到既有 Phase 修复，不得以“删除阶段顺手重写”为名扩展架构。

## 2. 永久 KEEP 契约

- LangGraph Lead runtime、middleware 主链、普通 subagent、timeout/cancel/token/receipt/loop guard。
- Auth、Thread、Run、SSE、Artifact、Upload、Scheduler 与 PostgreSQL persistence/checkpoint。
- Analytics domain/application/infrastructure、MySQL/PostgreSQL datasource、安全 SQL、审计、报告与 UI。
- Local sandbox 与 AIO/Docker sandbox；`present_files`、`ask_clarification` 和必要文件/命令工具。
- Skill runtime，但只保留经营分析、数据分析、图表/报告和最小基础技能。
- MCP client 的 discovery/session/invocation；任何数据访问仍不能绕过 Analytics policy。
- OpenAI-compatible 与 DeepSeek 模型主路径。
- 一个可选 Web Search/Fetch 主路径；默认候选为 Tavily，最终以真实 import/config/tool 流证据裁决。
- 中文优先的 InsightFlow 前端、登录、分析、datasource、metric、report、history、scheduler、settings。
- Phase 0–4 建立的安全测试、关键 runtime 回归和发布级 acceptance contract。

## 3. 候选 DELETE 域

删除必须按下面的域审计，不能把多个域混成“misc cleanup”：

1. **Frontend legacy surface**：public docs/blog/showcase/github-stars、Custom/Managed Agent UI、
   Projects/Documents/Trash、Channels、Browser、Voice、Capability marketplace，以及孤儿营销组件。
2. **Channels/IM**：Slack、Telegram、Discord、DingTalk、Feishu/Lark、WeChat/WeCom、Buzz、GitHub
   channel 的 router、OAuth/webhook、lifecycle、config、persistence、frontend 与 SDK。
3. **Custom/Managed Agents**：agent marketplace/editor/SOUL 管理、managed subagent CRUD；保留代码内
   固定的普通 subagent runtime。
4. **ACP 与 durable batch**：ACP external agents、batch_task 持久化/API/UI；保留普通 `task` 委派。
5. **Projects/Documents/Trash/Browser**：解除 thread/artifact/scheduler 对它们的引用后删除；不能破坏
   thread ownership、artifact 下载和分析历史。
6. **Remote sandbox/provisioner**：E2B、BoxLite、OpenSandbox、Tenki、Kubernetes provisioner/Helm；
   保留 Local + AIO/Docker。
7. **Provider zoo**：专属 Claude/Codex/MindIE/MiMo/MiniMax/StepFun/vLLM adapter、多套 search/crawl。
   保留扩展边界但不保留默认产品不使用的专用实现。
8. **Memory providers**：删除 Honcho、Mem0、OpenViking，保留 DeerMem/Noop 及业务偏好主链。
9. **Skill platform/media**：marketplace、self-evolution、creator/reviewer/find，以及图片/音乐/视频/播客/
   PPT/web-design 等非经营分析技能；保留 loader/policy/activation 与业务分析技能。
10. **Dependencies/config/tests/docs**：只在活跃引用清零后删除对应依赖、配置、测试、文档和 CI job。

## 4. Phase 4 视觉遗留

认证页仍引用 `frontend/public/images/deer.svg`。Phase 5 前端删除批次必须先移除这两个页面的
`mask-[url(/images/deer.svg)]`，复用现有 Lucide/CSS 几何图形或无装饰布局，不新增生成图片；随后只有在
全仓真实引用为零时删除该资产。最终保留页面不得展示 DeerFlow 鹿标识。

## 5. Phase 5A 清单契约

Phase 5A 只做审计与清单，不修改生产、测试、依赖或配置。提交以下文件：

- `docs/removal/phase-05-current-inventory.md`：基于 `git ls-files` 的当前规模和最终 KEEP 表面。
- `docs/removal/phase-05-deletion-manifest.yaml`：机器可读的删除/修改/保留项。
- `docs/removal/phase-05-dependency-impact.md`：入口、静态/动态引用、配置、router、lifecycle、DB、测试、
  dependency、replacement。
- `docs/removal/phase-05-verification-matrix.md`：每个删除批次的 focused 与累计门禁。

Manifest 顶层必须有 `baseline_commit`、`baseline_tree`、`target_budget`、`batches`。每个 batch 必须有：

- `id`, `objective`, `delete_roots`, `delete_files`, `modify_files`, `keep_exceptions`；
- `entrypoints`, `dynamic_references`, `config_keys`, `dependencies`, `tests_to_delete`, `tests_to_keep`；
- `replacement`, `preconditions`, `focused_gates`, `cumulative_gates`, `rollback`；
- `before`/`forecast_after` 的 tracked/source/test/text-LOC 统计。

目录项必须配 `keep_exceptions`；单文件项必须使用 repo-relative exact path。不得用 `**/*`、“related
files”“etc.” 或未经展开的模糊 glob。YAML 必须能被仓库现有 Python 环境解析；不得为解析清单新增依赖。

## 6. 引用证明

每个 DELETE 项至少检查：

- Python/TypeScript import、re-export、lazy import、字符串模块路径与 `config.yaml use:`；
- FastAPI router、lifespan、middleware、extension/plugin/skill/tool registry；
- Next.js filesystem route、dynamic import、navigation/i18n、mock/static route；
- Compose/Makefile/scripts/CI/env/config/docs；
- migration/table ownership、runtime metadata/protocol key；
- 测试 fixture、snapshot、E2E network mock。

“`rg` 无普通 import”不等于无引用。动态引用必须记录具体入口和解除方式。历史 migration 若仍需从空库
升级则默认 KEEP；只有 Phase 6 证明全新 squash migration 可替代时才另行裁决。

## 7. 删除批次与回滚

Phase 5A 应给出 3–5 个依赖有向、可独立回滚的执行批次。推荐顺序：

1. Frontend legacy routes/brand assets；
2. Channels + Custom Agents + Projects/Browser 产品面及后端入口；
3. ACP/batch + remote sandbox + provider/memory zoo；
4. Skills/media + dependency/config/docs/tests cleanup；
5. 最终 orphan/reference/size convergence。

实际批次可根据依赖证据合并或调整，但不得把所有删除压成一个不可审查提交。每批提交前后都要有精确
文件数、引用扫描和门禁；回滚使用该批 commit 的 `git revert`，不能依赖手工恢复。

## 8. Phase 5A 验收

- 仅文档发生变化；工作树干净、固定 tag/tree 和 lockfiles 不变。
- 清单覆盖本规格十个候选域以及 `deer.svg`，无模糊路径和未分类候选。
- 每个 delete root 都有入口/动态引用/config/test/dependency/replacement 证据。
- 预测总量按批次可加和，明确是否能达到 850–1050；达不到时给出保守最低值和不可删 KEEP 成本。
- 测试清理按“删除模块删对应测试、KEEP 主链保留关键测试”，不能按文件数比例裁剪。
- Phase 5B 未启动，任何生产文件删除数为 0。

