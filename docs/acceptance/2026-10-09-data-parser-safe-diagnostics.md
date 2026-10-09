# Data parser 安全诊断定点修复

只在 `roles.py` 已有五个 `numeric_validation_failed` 分支写入固定警告消息：`analysis_data_parser_rejected.{reference_domain|claim_domain|label_domain|claim_label_ids|numeric_verification}`。消息不拼接输入、ID、数值、异常或堆栈；公开失败码及解析/验证规则保持原样。

新增回归覆盖五个拒绝分支：断言外部仍为 `numeric_validation_failed`，每次只产生对应固定消息，消息参数为空且没有异常信息；合法声明仍验证成功且没有拒绝日志。

定点测试通过：

```powershell
& '.venv/Scripts/python.exe' -m pytest 'tests/test_analytics_agent_roles.py' -k 'data_parser_rejection_logs_only_fixed_reason_and_preserves_public_code or valid_data_parser_response_has_no_rejection_log' -q
# 6 passed, 16 deselected
```

缓存断言修正后的最终检查：

```powershell
& '.venv/Scripts/python.exe' -m pytest 'tests/test_analytics_agent_roles.py' -q
# 22 passed
& '.venv/Scripts/ruff.exe' check 'app/analytics/agent/roles.py' 'tests/test_analytics_agent_roles.py'
# All checks passed
& '.venv/Scripts/ruff.exe' format --check 'app/analytics/agent/roles.py' 'tests/test_analytics_agent_roles.py'
# 2 files already formatted
```

Principal 确认 `_invoke_role` 的缓存命中按契约设置 `cached=True`，首次调用为 `False`。原完整 dataclass 相等断言已改为分别比较 SQL、input/output token 字段并断言缓存标记；保留原 `len(role_calls) == 3`，确保缓存没有重复调用模型。

无外部模型调用、部署、容器操作或前端改动。
