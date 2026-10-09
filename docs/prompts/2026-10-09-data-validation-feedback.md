# 既有Data两次尝试增加安全校验反馈

gpt-6-luna/max。主会话已独立执行现有failure-summary：唯一自动scheduled run最早Data numeric_validation_failed，固定日志numeric_verification；PG恢复passed。调度确自动触发但报告失败，不能冒充AS11passed。根因具体NumericClaimError已提供稳定reason但被role汇总代码丢失，下一尝试没有纠错反馈，导致重复相同输入。

所有权roles.py、test_analytics_agent_roles.py、docs/acceptance/2026-10-09-data-validation-feedback.md；其它生产只读，不部署/模型。复用现有每role锁、scope、2次总attempt、timeout/cache，不加自动重试循环/额外模型调用或新框架。

最小改进：_parse_data_result对NumericClaimError单独处理，只保留其**已有闭合枚举reason**作为内部安全诊断/私有失败信息（reference_unavailable/value_mismatch等，允许映射固定提示），公共reason仍numeric_validation_failed；不记录候选/数值/SQL/error正文。不吞未知Exception，未知仍原failclosed。

Data能力对同一payload fingerprint首次数字校验失败时，记一条固定内部校验原因；仅在现有允许的第二次相同调用里，将该固定原因及“请修正引用/计算，保持闭合结构”指令加入模型消息。不要回传原模型自由正文、数字或任意异常文本；不同payload不能复用反馈，不改变fingerprint/cache合法成功、attempt cap/sdk zero retries、回调隔离。首次数值伪造仍被拒绝，第二次也只有正确引用/算式/数值通过原verify才接受；不得计算替换模型错误值、放宽验证或增加attempt。

回归用现有mock证明同payload首次数值失配→第二次消息有固定feedback且合法response成功；一直失配最多2次且拒绝；不同payload不漏反馈、成功缓存不调用；公开码仍旧且无数据日志。运行该file一次+两文件Ruff/static，避免全suite。

先交精确patch/tests/风险后冻结，Principal审查后才部署/允许一次新的scheduled验收。原失败task/claim不动，不盲重发；后续cancel/checkpointpending可另切片完成。
