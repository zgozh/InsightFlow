# Data 数字校验反馈

唯一 scheduled run 的最早失败为 Data stage 的 `numeric_validation_failed`，日志只证明固定分支 `numeric_verification`；旧 run 未持久化更细的 `NumericClaimError` reason，因此具体数字校验子分支未知。`numeric_claim_value_mismatch` 是离线 mock 使用的闭合原因示例，不能当作 live 根因。角色解析器此前把 `NumericClaimError` 与所有异常合并处理，只留下通用公开码；主会话独立证据指出，同一输入的第二次既有尝试没有收到纠错提示。

`_parse_data_result` 现在单独处理 `NumericClaimError`，日志仅带已有闭合原因码，公开异常仍为 `numeric_validation_failed`。Data 角色仅按 canonical payload fingerprint 暂存该原因；同一 payload 的第二次既有调用才会消费它，并收到固定的“按当前证据修正引用或计算、保持 claims/labels 闭合结构”提示。模型自由文本、数值、查询内容和任意异常文本不会进入反馈。未知异常继续走既有 fail-closed 路径。

反馈不更改 fingerprint、成功缓存键、证据范围、数字算法或验收条件；第二次响应仍须通过原 `verify_numeric_claims`。最多两次角色调用、provider SDK zero retries、scope、锁、超时和回调隔离保持原样。无真实模型请求。

离线 mock 覆盖同 payload 首次失配后第二次合法结果、连续失配停在两次上限、不同 fingerprint 不继承反馈、成功缓存不再次调用，以及未知异常不转成数字反馈。AS11 的此前 scheduled run 仍是失败结果，本改动不把它改记为通过；新的 scheduled 验收须由 Principal review 后另行决定。
