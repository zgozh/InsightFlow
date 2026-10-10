# 唯一剩余指引长度门禁

实施者gpt-6-luna/max。CI commit1f7639e的Lint run38033361479只有agent-guidance失败，frontend/backend lint都success。错误：backend/packages/harness/deerflow/runtime/AGENTS.md有效继承链98651字节，hard98304，仅超347；另4项soft warning不是fail。不修改checker、workflow或上限。

只拥有backend/AGENTS.md（含本轮新隐私一句与重复上层说明），及必要实际runtime/AGENTS.md重复文字压缩须报告，不改CLAUDE/代码/测试/其他文档。安全约束保留，压缩重复介绍/命令/冗长语句至少约1KiB，使实际Linux UTF-8/LF继承链低于hard并留小余量；不得为减字删除关键鉴权、调度、持久化或隐私承诺。读取真实check_agent_guidance脚本/CI调用定位路径，V0跑同一指引门禁，检查实际diff。仅修这一个confirmed失败，不重跑unit/E2E或格式全仓。

当前 Gateway发布worker只写ignored部署材料并读取4生产源文件，文件所有权独立。你不做Docker/模型操作。

完成freeze返回具体diff/字节数/检查命令及结果，不commit/push。Root复审后正常提交该指引及本prompt，新CI只看真实结果；uv.lock不动。权限dangerfullnever不sandbox_permissions。
