# Phase 6F2：AS-14 受控分析安全边界定点验收

你是 InsightFlow 实施 Agent（`gpt-6-luna`，`reasoning_effort=max`）；GPT 负责方案与独立复验。起点应为干净 `main`、HEAD `1bae353`。先核对起点、固定 `upstream-v2.1.0-rc0` tag/tree 与工作树；不符即停止报告。只读全局、根及实际涉及模块的 `AGENTS.md`，再读 `docs/acceptance/acceptance-scenarios.md` 的 AS-14、`docs/acceptance/phase-06d-contract-reconciliation.md` 的 AS-14、`docs/acceptance/phase-06f1-real-analysis-rehearsal.md`，以及本切片直接涉及的工具装配、Gateway 准入、writer capability 和现有测试。不要重读整个架构史。

## 目标与不变量

目标是判断 AS-14 **按用户已批准的边界**能否从“发布阻塞”提升为“已验收”，并补齐真正缺失的定点证据。平台托管 Analytics 查询经过 Query Policy、授权、成本/限额、超时与审计；普通聊天保留 operator 配置的通用 MCP，但不声称第三方 MCP 遵循相同 SQL 策略；受控分析运行在模型可见和最终执行两处只允许 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`，不暴露 MCP、命令、任意文件、动态插件、委派或未知工具。Gateway 只凭受信身份、持久 `kind=analysis`、仍可用的 Analytics services 与 run-scoped writer capability 准入，任一条件失效则 fail closed。6F1 已有真实 NGINX/认证/DeepSeek Flash/PostgreSQL/evidence/report 正向链路，不得因本轮重新发模型请求来“增加信心”。

## 连贯工作切片

1. 先做**条款—证据表**：逐条对照 AS-14 原文，标明代码入口、既有测试 ID、6F1 实机证据与尚无证据的边界；明确区分静态/合成/真实环境，不用“测试通过”概括全部。重点追踪模型绑定工具与最终 ToolNode 是否同一个固定集合；伪造/历史 `tool_call`、`tool_search`、MCP 缓存/热更新、MCP task notification、客户端伪造 analysis context、旧 chat 线程、服务/writer 失效；普通聊天 MCP 不被误禁。
2. 对已有证据仍有效的行为，不重跑 6F1 的 Docker/模型/数据库或整个后端/前端套件。只对**当前证据无法闭合的条款**运行最窄测试：优先 `backend/tests/test_analysis_tool_allowlist.py` 中对应用例、`test_gateway_services.py` 的 analysis 准入/伪造/writer 用例、`test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get`、报告 writer 权限直接用例，以及前端 `analysis-entry-activation.spec.ts` 中对应行为。先检查现有测试是否已给出独立的模型可见/最终执行证据，避免重复跑有效门禁。若只有源码可证明路径不可达，可用清晰调用图与定点断言，不必硬造 live MCP 服务器或模型调用。
3. 若确认一个**真实且直接影响 AS-14** 的缺口，先可复现地说明入口和影响，再做最小修复及一条保护行为的回归测试，仅验证受影响模块/契约。不得为理论风险增加通用注册表、防御包装或新依赖。若需要改变固定工具集、放宽 Gateway 准入、引入子 Agent/Reviewer、修改 AS-14 产品承诺或跨越大量文件，停止并向 GPT 报告设计选择，不自行扩权。
4. 最终在 `docs/acceptance/phase-06f2-as14-boundary-evidence.md` 写中文证据表：每条原文对应何种证据、实际运行的命令/退出码/计数、未运行与原因、剩余风险。只在**全部已批准条款有充分证据且无确认缺陷**时同步把矩阵、场景现行状态和 `docs/PROGRESS.md` 的 AS-14 状态改成准确的“按批准边界验收”；否则保持“发布阻塞”，列出精确的最小未闭合项。6F1 的单次实机样例不能证明任意第三方 MCP 安全，也不能替代 AS-01..AS-15 全部场景。

## 验证级别、交付与停止

这是 V3 安全/发布边界，但“V3”不等于默认全量：先审查现有证据，随后只跑缺口对应的 pytest/前端定点测试，若有生产修复则检查受影响 Ruff/类型/格式；文档-only 结论用 V0 readback 与 `git diff --check`。仅当窄证据不能排除真实旁路时升级，并说明为何升级。不得运行 14k 后端、全量 Playwright、重复 6F1 模型请求、清理或重建保留的演示容器/卷；不读取/输出真实 `.env`、`config.yaml`、环境变量值、SQL 原文、token、凭据或结果行。

按一个相干切片提交；如确认需要生产修复，可拆为“定点修复提交 + 证据文档提交”，每个提交边界清楚。报告 commit/parent、精确文件集合、实跑门禁、条款结论与未验证项；工作树干净后停在 GPT 复验，不启动 Phase 5C、AS-07/08 的角色改造或下一阶段。不要把 AS-14 通过等同 Phase 6/发布整体完成。
