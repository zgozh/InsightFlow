# 直接查询API安全验收

gpt-6-luna/max。主会话已审查成功正例的证据摘要：run成功、报告发布/数值/证据scope/下载/普通用户页面通过。现在直接测试现有query-plans/query-executions API，**不调用模型，不重复正例**。

所有权 `.reviews/final-postgres-runtime-20261008/security-probes/`、`docs/acceptance/2026-10-09-direct-query-security.md`。生产只读，不改角色/前端/部署/旧29384；不改现有B正常policy。复用原DPAPI身份和成功context/已存在source，引用现有probe而非重造框架，脚本写文件后执行，禁node -e长命令。

读取实际router/models直接契约，复用既有CSRF/login，执行有界API矩阵：匿名401；B管理403；未授权/不存在source、未授权表/列（description/customer_email）、DDL/DML/事务/多语句/注释Unicode边界拒绝；合法只读plan→execute成功、一次性plan重放拒绝、他人主体不能执行Bplan。保留结构化audits和响应闭合无SQL/plan token/credentials/results意外透传的证据，允许的执行结果字段按现行契约判断，不虚构“所有响应无行”。HIGH拒绝和MEDIUM裁剪/实际超时按现有适用测试及真实adapter证据复用；如要追加fixture只可独立合成资源，不修改B正常授权。

优先完成这个无模型HTTP矩阵，命令/稳定code/计数/hash即可，禁输出SQL/密码/原始结果/body。不得把无法实测项写passed；列明需要后续补的精确一项，不扩大全套测试。失败若只是fixture参数/响应形状不匹配，以实际契约最小修fixture；产品缺陷先交具体定位，不擅改生产。

V3的剩余安全边界，当前仅上述API。结束短记录冻结，主会话随后推进调度/重启/checkpoint/取消，不要求用户再确认。
