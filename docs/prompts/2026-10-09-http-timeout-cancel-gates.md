# 最后HTTP超时、取消与未完成恢复边界

gpt-6-luna/max。独立所有权 `.reviews/final-postgres-runtime-20261008/http-final-gates/` 与 docs/acceptance/2026-10-09-http-timeout-cancel-gates.md，其他生产/脚本/文档只读。当前另外worker只做scheduled/PGcollectorproof，不与他们DB资源冲突；不要Gateway restart直到他们全部冻结。root审批后才能恢复restart。

AS06剩余是HTTP真实timeout+audit。现有query policy禁止pg_sleep，不得放宽。可在**现有独立合成PG业务库**用fixture owner新建一个唯一测试view，底层view中pg_sleep(6)（不改任何原表数据/原view），对独立readonlyrole grant SELECT；注册独立source/schema/normal列policy。用户API只执行合法允许view SELECT，EXPLAIN无ANALYZE合法后执行实际5s timeout，记录execution_timeout/对应audit/活动连接已清理。测试结束disable合成source、drop独立view，原fixture/权限保留。管理员server独立view是受控外部fixture，不是给用户危险函数权限。使用既有PG owner DPAPI/网关envsecret只在内存，禁输出credentials/SQL/results。若成本classMEDIUM实际timeout2.5s如实记录，不硬期望5s。验证实际viewvolatile函数没被planner省略，否则改viewfixture而非policy。不要创建新container或改global config。

AS08 livecancel：允许**最多一次**新增cancel用run（不要混用schedulerrun），新独立合成thread，非破坏性问题；优先用现有gateway run无模型mock/阻塞fixture。若没有runtime支持mock，可真实模型新run在收到metadata/runID后立即POST取消（native fetch/HTTP stream只等首metadata，不PlaywrightAPI等整流），确保not success、structuredcancel/terminal与worker底层取消，保持费用最小，不等生成业务报告。所有ID创建即私存、claim独立，零重复发起。真正缺必要contract先给精确endpoint，不泛扫。

unfinished recovery需要最小真实证明：若上述run能用已受控本地阻塞fixture挂起，保存运行running后与Principal协调一次Gatewayrestart验证error/interrupted而非success；不写假running数据库行、不绕恢复机制。若只有付费模型可用且易race，请先做livecancel并提交证据后冻结，随后由Principal安排最后必要恢复，不为测试侵入productionruntime。

执行最短几条API，不重跑已通过matrix/rowscaps/report/UI/PGrestartpast，不做新框架。安全结果/status/code/audit/hash即可，实际失败精确记录，不宣称未跑门禁passed。当前dangerfullaccess/never不用sandbox_permissions。
