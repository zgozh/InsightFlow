# Reviewer 新增注释中文化（V0）

gpt-6-luna/max，仅修改本次SDK修补在 reviewer.py 新增的英文解释注释：异步专用副本丢弃同步client、保留原Lead绑定身份、未知SDK形状失败关闭等说明。根AGENTS要求新增自有注释中文优先。

所有权仅 backend/app/analytics/agent/reviewer.py 中此次新增/改动的注释，以及既有SDK验收记录一行说明。不得改任何可执行语句/标识符/稳定日志/测试，也不批量翻译旧上游文件。backend阶段worker不拥有Reviewer，此文件无并行写者。

V0 diff/readback证明只改注释即可，不跑pytest/Ruff/全套，不让文案仪式延长开发。快速冻结后返回差异性质。
