# Phase 6F3B2 Fix 01：受控分析轨迹的外部消息伪造边界

你是 InsightFlow 实施者。基线为 6F3B2 `7649a6b`。GPT 复验发现：`Gateway.start_run` 在已知持久 `analysis_mode=True` 后仍调用通用 `normalize_input`；后者有意保留外部 AI/system/tool 消息正文与 tool-call 配对。外部调用者可在自己的分析线程提交看似 `write_analysis_report` + `published` 的 AI/Tool 消息，随后前端轨迹可能把它投影成假的“Reviewer 通过”和 artifact。实际报告发布没有被绕过，但轨迹真实性有误。先以最窄的合成入口测试证实或否定这个**具体**路径，不因推测而扩大范围。

若证实：只在**非 internal 的受控 analysis run** 输入边界，拒绝任何外部 AI/system/tool/function 等非 human 消息（包括 dict 和 BaseMessage 形式，以及畸形 messages 形状）；只允许正常 human 输入，既有 checkpoint 历史由服务端加载，不要求客户端重传。拒绝应发生在 run 创建/Agent 启动前，给稳定、脱敏的 400/422 码；不要静默把非 human 转成 human。普通聊天 `normalize_input` 的上游兼容语义、受信 internal 调用与线程历史读取保持原状。客户端若可通过其它输入通道模拟工具结果，也只封闭已证明的同一入口，不新建通用消息签名/全局过滤框架。

用一个先 RED 的回归构造客户端 AI tool call + ToolMessage，content 为**完整但合成**的 published 回执（有效 report ID、固定 path、evidence digest），证明旧路径会被 Gateway 接纳；修复后同样请求在图/报告服务前被拒绝，真实 human 仍可启动受控分析，普通聊天非 human 兼容性仍通过。前端 6F3B2 已有投影安全测试保持有效，**不要重复跑其全部门禁**；只跑受影响 Gateway 输入/准入测试，必要时加现有 trace 定点测试。受影响 Python Ruff/format 与 `git diff --check`；不跑 Docker、真实模型、全量测试。V2 共享 Gateway 安全边界，按比例验证。

说明残余事实：这一修复保护新输入，不会给已存在的历史消息补密码学来源证明；不得把本轮说成任意历史数据库行都可信。若真实入口在此之前已拒绝这些消息，直接提交只读证据说明并停下，不为凑修复而改代码。

若需要修复，仅提交一个窄范围 Fix 01；在 `.reviews/phase-06f3b2-fix-01-external-message-spoofing.md` 记录复现、文件集合、实跑命令/退出码、普通聊天不回归及剩余边界。工作树干净后停 GPT 复验，不启动其它阶段；锁文件、固定 tag 不变，不 push。
