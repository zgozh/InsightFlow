# Phase 6F3F7：同一已发布报告的数字与 evidence 溯源复核

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。6F3F6 `74410f0` 已通过 GPT 定点复验。只读复用已有 run `63cfc92a-97d9-446d-ad21-58d71ff97821`，不创建新 run、报告、管理员或数据库记录，不发模型请求。

## 为什么做这一轮

真实浏览器已证实报告卡下载和分析轨迹可见，但 AS-10 的报告数字是否来自同 run 的受控查询结果仍未核验；AS-09 矩阵还停留在 6F3F2 “trace trigger 未挂载”的旧事实。用现成的合成业务数据和现有报告做一次有界审计，比再跑一次完整 Agent 更便宜、更能说明当前报告的可信度。

## 范围与证据

验证级别 V3 的**只读验收审计**，不涉及产品代码修改或应用测试。先最小阅读 `.reviews/phase-06f3f6-report-card-download.md`、`docs/acceptance/phase-06d-contract-reconciliation.md` 中 AS-09/10 行、同 run 已有 6F3E10/6F3F1 记录，以及取回该 run 报告和查询 evidence 所需的直接代码/数据契约。沿用已有 owner 凭据的安全读取机制；不输出/保存密钥、cookie、原始 SQL、结果行、报告全文、模型自由文本或 artifact 正文。若报告/工具消息原始数据不能在不泄露的条件下获得，记录阻断并停止，不猜测。

仅在短生命周期进程内读取这个**合成**报告正文及与其 evidence ID 对应的同 run 成功查询结果，做手工/程序辅助的逐条对照：

1. 报告引用的 evidence ID 是否都能对应同 run 的成功 `query_business_data` 结果；没有孤儿引用或跨 run 拼接。
2. 报告中可核算的关键数字、汇总、分母/百分比与单位/期间，是否能从对应结果行推得；记录安全分类计数 `supported / unsupported / ambiguous / not_numeric`，不要输出原始数值。若缺查询数据或口径不明，归为 `ambiguous`，不得伪造通过。
3. 若能按既有 `AnalyticsQueryEvidence` canonical 规则复算 result digest/evidence ID，则核对；若需要新实现或原始数据不可得，只记录“未复算”，不要为单例新增框架。
4. 核对引用顺序与 Reviewer `rejected → approved`、最终 `published` 记录一致；不把 Reviewer 通过等同于数字正确性。

如需一次性脚本，只放 ignored `.reviews/`，先限定输入为该 run/owner，不写业务数据库、配置或提交敏感记录；脚本输出只含安全计数、布尔和稳定原因分类。不要额外跑数据库集成、前后端测试、Docker build 或浏览器流程。已通过的 6F3F5/6F3F6 浏览器证据保持有效。

## 文档与交付

用新证据最小修订 `docs/acceptance/phase-06d-contract-reconciliation.md` 的 AS-09 旧浏览器描述：6F3F5 已在真实页面看到 trace trigger/panel、catalog/query/report steps 和 Reviewer rejected/approved；但**仍未**证明完整 live SSE 阶段与自由文本绝无思维链。AS-10 只在本轮确有数字溯源证据时追加相应限定；不把单例变成通用保证。必要时在 `docs/PROGRESS.md` 加一句阶段结论，不重排历史。文档变更按 V0 读回、diff check，不跑应用测试；独立提交，工作树干净。

脱敏报告放 `.reviews/phase-06f3f7-existing-report-provenance.md`，记录数据来源/读取范围、计数与不可核验项、AS-09/10 修订依据、是否有确定产品缺陷；绝不附 SQL、行值、报告全文或凭据。若发现确定的数字错误，只报告最小安全事实和根因候选，停在 GPT 架构复验，不自动重跑模型或扩大修复。完成后向 GPT 交报告，不启动下一阶段。
