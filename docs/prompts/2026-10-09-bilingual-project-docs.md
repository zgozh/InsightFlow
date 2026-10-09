# InsightFlow 双语项目文档收尾

实施者 gpt-6-luna/max。读取根 AGENTS。用户授权：默认中文README，仅中英文，删除多余语言与过时无用文档，详细说明个人开发的企业级项目；验收通过才commit/push。你**不执行git commit/push**。

独立所有权：根 `README.md`、`README_en.md` 及现有其它语言 README（可删除）；根 `AGENTS.md` 仅修README语言链接/默认语言约定；`docs/current-capabilities.md` 与你自己新建的 `docs/acceptance/2026-10-09-bilingual-documentation.md`。其它代码、backend/frontend AGENTS、PROGRESS/INTERRUPTION、prompts、其余验收记录、部署脚本均只读，不与当前运行验收worker重叠。

1. 先读现有中英README、current-capabilities及最新PROGRESS、最新真实正例/契约验收记录；不读整仓历史计划。参考原DeerFlow官方README与一个相近官方Agent项目文档的结构，用户明确要求参考，须浏览官方源码/文档（非搬运正文）。产品文字突出InsightFlow实际开发贡献，同时保留LICENSE及必要原创归属，不能伪称所有底层原创。
2. 默认README.md为详细中文，README_en.md对等英文，仅两种版本；删除README_zh以及其它语言版本，修正自己所有权文件内语言/链接。包含定位与截图/演示资源（只能真实已有）、普通用户/管理员操作流程、实际界面入口、架构数据流、复用底座与新增治理边界、Agent/工具/MCP/checkpoint/持久化与报告、SQLite默认/可选app PG/外部业务PG关系、四服务默认部署、配置与凭据、最短上手和常见空目录原因。不要宣称不存在的数据源/指标picker。不要把后台支持写成UI可操作功能。
3. 当前真实状态：新29388是独立验收入口、旧29384不是已更新发布入口；合法查询3行成功，Data阶段live报告正例仍失败；numeric/parser离线可验证3901.25；22角色测试passed。当前worker正在最小Gateway诊断更新和一次新run，**你不要写最终验收完成**。用明确的当前已验证/待验证说明，后续Principal最终汇总再更新。
4. 其它过时文档只形成短的精确删除/保留候选表，列路径、实际过时原因、引用影响；先不删除自己所有权之外文件，避免误删仍需的部署/安全/架构或验收证据。不要新增庞大文档体系。root AGENTS参考链接指向中文README和英文README，不能删除法律/技术包名。
5. V0：只读回/链接路径检查/git diff --check；不运行应用测试/build/E2E。交回实际变更文件、引用检查结果、删除候选后冻结。
