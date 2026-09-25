# Phase 6E2A Fix 01：线程创建的 kind 幂等冲突

起点 `main`/`0ce3ff4`（本提示词提交后以新 HEAD 为准），工作树干净。按全局与仓库 `AGENTS.md`、6E2A 原提示词执行。只修复本次审查确认的单一边界，不启动 6E2B。

问题：`routers/threads.py::create_thread` 对已存在的 `thread_id` 直接返回旧记录；`IntegrityError` 并发插入恢复分支也如此。若请求 `kind=analysis` 而旧记录是普通聊天，响应 200 会制造“受控分析线程已创建”的错误认知。反向的 `kind=chat` 请求也不应把已有分析线程当同类幂等成功。

要求：同一 ID、同一持久 kind 才可幂等返回；kind 不一致时返回稳定、脱敏的冲突响应（建议 409 `thread_kind_conflict`），不得修改旧记录或 checkpoint。两个返回旧记录的路径必须共用该判断。旧线程无 analysis 标记等价于 `chat`；显式标记损坏、元数据解码失败须 fail closed，不能按 chat 放行。若内存 store 的并发同 ID 创建存在覆盖旧 kind 的真实路径，给出直接证据并最小修复；无法安全闭合时停止，不虚报通过。

先写一条有价值的回归覆盖 chat→analysis、analysis→chat、同 kind 幂等，以及并发 `IntegrityError` 恢复分支；确认目标 RED 后做最小实现。级别 V2（共享创建契约和安全标记），只运行直接受影响的 thread router/存储定点检查和改动文件 Ruff、diff；已有 6E2A 其他门禁证据只在行为面被影响时重跑，不跑全仓/Docker/E2E。测试只用合成值，不读取或展开真实环境/密钥。一个独立修复提交，报告 commit/parent、文件集合、真实执行的门禁、偏差与未验证项；停在 GPT 复验。
