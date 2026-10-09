# Data 契约与前端入口定点检查

gpt-6-luna/max。读取根/backend/frontend AGENTS，用户强调复用成熟底座、最小修改和真实前端可操作性。本切片禁止模型调用、容器操作与架构扩展。

主会话已读 roles.py 的 _DATA_PROMPT/_parse_data_result 与失败记录。首次查询成功；精确 live 数值失败子分支未知。不要再枚举live运行，不为未知原因盲改。

所有权：`.reviews/final-postgres-runtime-20261008/runtime-probes/` 中本切片自己的离线检查文件，及 `docs/acceptance/2026-10-09-data-contract-and-ui-entry-review.md`。生产只读，若确认缺陷交建议后冻结。

1. 复用现有 backend/tests/test_analytics_agent_roles.py 夹具与实际 _parse_data_result/verify_numeric_claims，构造本次月度3行收入的合法 cell/月度period引用和sum声明，未知币种unit=null，标签不含数字。用现有 backend环境无模型重放，验证两位小数/月度期间引用/总计3901.25。只跑这份小检查，不跑整个已有测试集。核对 prompt 与 operation 枚举/列类型/decimal编码/row引用是否有实质不一致，明确发现或未发现，不把猜测写成根因。
2. 只读检查前端 `/workspace/analysis/new` 与普通聊天、导航、数据源/指标/报告/审计/调度页面，形成精确操作路径（中文实际名称、需要哪个角色、资源怎么进入分析上下文、是否存在数据源选择控件）。不得把后端支持等同于UI支持；区分现有入口和缺失。关注 chat-page.tsx、对应路由、analytics API/hooks、scheduled-tasks 即可，不全仓扫描。
3. 若离线合法输入成功且live原因仍未知，建议最小诊断方案：在**既有 parser 的具体失败分支**记录仅固定枚举的服务器内部原因，不记录候选/body/SQL/值，也不改公开错误码/事件schema/权限/验证规则。不实施，先交Principal审查。不要增加观测框架或兼容包装。
4. 短记录+精确commands/results+建议后冻结。最终验收/文档清理/commit push仍未完成，不要宣称发布完成。
