# 角色基础独立审查修补

实施 gpt-6-luna/max，接续已冻结 roles 切片。所有权仅 roles.py、其测试、该角色验收记录；暂不改 Reviewer/Gateway/工具/domain。主会话已读完整 roles.py 并确认两个实际边界缺口，修完后再冻结，不扩展通用框架。

## 模型合同提示不完整

Data 系统提示称“字段结构按请求约定”，但 payload 仅 snapshots/metrics，没有给出 claim/reference 字段、operation enum、value 必须为普通十进制字符串或 nullable 引用约定；Writer同样未给出 kind/claim_ids 结构。fake测试知道合同，真实供应商并不知道。将完整闭合响应schema与固定运算/arity/舍入规则写入该角色中文提示或请求中的固定 response_contract。标签禁止包括汉字数在内的 isnumeric 字符，期间与单位只能用引用；不要添加自由正文。Writer明确sections/kind/claim_ids格式与三个enum。

`analyze` 增加 keyword-only `analysis_request: str = ""`，由下一工具接线把原 markdown/draft 请求传入。输入最长8192字符、trimmed、合法UTF-8，空字符串允许既有测试，但生产工具会提供有意义请求；纳入payload和成功缓存指纹。它是待处理的不可信目标文本，不直接发布。补一个目标进入模型与改变缓存指纹的定点行为断言。

## OpenAI SDK 实际重试未禁用

本机 langchain_openai/chat_models/base.py 显示 max_retries 仅在 model初始化时传入 root_async_client，而 ainvoke 实际使用已创建 async_client。只 model_copy(update={max_retries:0}) 会复用原SDK client，不能证明重试关闭。

ChatOpenAI 专用复制必须同时为异步 SDK root client 调用其 `with_options(max_retries=0)`，将副本 root_async_client 与 async_client 指向对应新root.chat.completions（Responses路径也使用新root），保留现有http连接配置且不关闭Lead client；同步root/client如保留同样隔离。若无法得到受支持的 SDK options/client形状就 fail closed，不静默接受。不得修改Lead实例、打印client/密钥或重新构建client时读取环境变量。其他Base模型不可仅因有max_retries字段就泛化承诺底层transport重试关闭。最小生产支持边界可明确限定ChatOpenAI；测试double可改为它的本地生成子类，但绝不能在生产代码按测试类名/模块放行或加入测试专用权限分支。不要添加供应商框架。

增加直接的真实SDK行为回归：ChatOpenAI使用httpx MockTransport返回500，SDK默认配置原本有重试；绑定角色后一次调用仅出现一个HTTP请求且稳定拒绝；不调用网络、不使用真实密钥，原Lead的SDK retries配置保持原值。同一fake测试证明模型callbacks隔离可继续保留。

V2：修后跑 roles 定点文件与Ruff/format，不跑整仓、不构建。uv锁不变。报告修补原因与准确结果，不声称已接线。已有PG适配真实验证冻结通过，与本切片无共享输出。
