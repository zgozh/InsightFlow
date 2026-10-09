# Data 解析拒绝分支安全诊断

gpt-6-luna/max，按根/backend指南。主会话独立审查确认现有解析器可接受合法三行月度证据及3901.25总计，但live失败的候选未持久化，无法定位。这次只补既有解析器的最小内部诊断，不重写Agent底座或放宽验证。

所有权：`backend/app/analytics/agent/roles.py`、`backend/tests/test_analytics_agent_roles.py`，以及短记录 `docs/acceptance/2026-10-09-data-parser-safe-diagnostics.md`。其它文件只读；不构建/部署/操作容器/发模型，不删原claim。

在 _reference_from_json、_claim_from_json、_parse_data_result 现有 numeric_validation_failed 拒绝点使用标准 logging，记录固定事件名和固定分支枚举（reference_domain、claim_domain、label_domain、claim_label_ids、numeric_verification）。只记录字面枚举，不记录候选内容、ID、数值、异常文本或堆栈；无需新配置、新包装类、新事件schema或公共错误码。保持原始异常对外行为一致，不把模型/provider响应泄漏到日志。不捕获/吞掉新的异常。

补最小持久回归保护这些日志不含输入内容、对外仍旧失败码、合法声明成功且无拒绝日志；尽量复用现有测试辅助/参数化。运行本次直接相关测试及两文件Ruff check/format --check，V1，不重跑整个后端/前端suite。

交回实际diff和精确检查结果后冻结，主会话审查，再安排最小镜像更新与有理由的一次新验收。不要自行再次发模型。原先失败记录和claim必须保留。

主会话追加审查裁决：现有缓存返回明确设置 cached=True，首次 cached=False，故成功用例的完整 dataclass 相等断言与该契约冲突。只修正该测试为分别验证首次/缓存标记，并保持 SQL、input_tokens、output_tokens 一致及只调用一次模型的原断言；不修改生产缓存。修正后只运行该测试文件一次及受影响文件静态检查，更新短记录，不宣称未验证的历史基线状态。
