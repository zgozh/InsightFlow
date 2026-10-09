# 历史发布门禁失败定点复核

gpt-6-luna/max。独立所有权 `.reviews/final-postgres-runtime-20261008/final-review/historical-gates/` 与 docs/acceptance/2026-10-09-historical-test-gate-audit.md。生产/tests/docs其它只读，不全suite、不Docker/model、不stage。

此前Phase5全backend测试13失败（14260passed）记录仍在，但不能默认当前仍失败或自动消失。用户要求验收后commit/push，需把这13项实际名/当前适用性明确。只读最直接Phase5B5日志/record、相关CI on触发条件，找exact失败nodeids。若已有后续有效passing修复证据直接引用；其余只跑这些**实际失败nodeids**一次，不重新跑14000项。

结果分类：当前任务回归需fix；已移除功能的过时测试契约不能改production把功能加回；真实已有unrelatedfail如实记录是否正式适用gate。不给每理论风险新增测试，不机械全suite。相关失败文件可能与Dataworker的 numeric/roles/reports/reviewer tests重叠，则先消息Root协调，不同时写（本slice不改任何tests）只read/run不影响writes；若文件正在更改就等冻结别读一半。

禁止为了PASS批量skip或放宽所有断言。只回精确current failure及最小修建议，Principal下一切片决定。若历史nodeids日志找不到，明确无法复核，不因为“保险”跑全部；必要查询文件名局部rg，不扫描全部cachehistory。

短记录具体命令/exit/passfail/适用workflow条件及仍缺gate，冻结。用户急完成，优先精确几条check，不长文档。
