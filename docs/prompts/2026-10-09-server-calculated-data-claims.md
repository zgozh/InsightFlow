# Data运算计划由现有确定性计算器执行

实施 gpt-6-luna/max。主会话已独立读 claims.py整段验证与roles：当前让模型填写计算结果value，再服务器计算并要求完全相等；多次真实scheduled Data失败，安全反馈未解决可靠性。收敛为成熟tool模式：模型选运算及证据，服务器算数字。不是放宽原校验器，也不是接受模型错误值。

所有权 domain/claims.py、agent/roles.py、直接相关 numeric/roles/reports/reviewer tests（必要mock响应跟内部协议调整）、backend模块AGENTS中一句计算职责说明、docs/acceptance/2026-10-09-server-calculated-data-claims.md。其他生产不动，不模型部署。

模型Data闭合输出只含id/operation/operands/decimal_places/unit_reference/period_reference及labels，**不再包含value或声称计算结果**。服务器构造“运算计划”并使用原Decimal512精度/ROUND_HALF_UP、原引用解析、snapshot内容校验/容量、算式种类/operand数、除零/非有限/大小限制，生成同一 VerifiedNumericClaim DTO；Renderer/Reviewer map/发布路径照旧。所有经营数字都仍有精确operand证据，单位/期间依然只能来自允许的单元格或null。

实现最小共享计算核心：原 `verify_numeric_claims` 的公开参数与行为完全保持，仍拒绝伪造assertedvalue；抽出有界共同处理逻辑，新增一个明确的server-calculation入口消费不含value的计划DTO（仅必要的小dataclass，不能新pipeline框架）。禁止通过 optional skip_validation 公共开关接纳模型value；模型提供value是协议extra字段拒绝，不忽略。公共verify显式声明依然严格相等，新增server入口由目标运行中服务绑定调用。

roles解析进入新plan→server计算，而不是模型断言值验证。保留schema闭合、label固定替代/ID集合、scope/cache/attempt2/sdkzero/安全反馈（引用/数据不合法仍有反馈，不再有模型算术失配）。不能用输出字符串猜期间，不生成自由数字正文，不添加其他model轮次。

持久回归：原全部numeric tests仍保护伪造value拒绝；server计算3月cell+sum=3901.25、precision/rounding、不合法ref/重复ID/不允许算式/除零/过大/nonfinite/unknownunit拒绝；roles新闭合结构拒绝带value/未知键、模型不需要算金额；报告透传真实VerifiedDTO且Reviewer拒绝仍零发布。只运行numeric/roles及受内部schema确实影响的reports/reviewer tests一次，四目标files套件是V2必要，不全backend/前端。changedfiles Ruff/format一次。

交代码、精确checks、明确兼容范围（仅内部Data角色输出协议；用户API/冻结evidence/SQL政策不变）后冻结。Principal独立review后才COPY domainclaims+roles部署一次新的scheduled验收，当前禁止付费调用。不要把旧failedruns更改成功，不再追加其它架构。
