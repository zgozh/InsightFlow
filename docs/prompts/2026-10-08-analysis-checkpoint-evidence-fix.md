# 显式 checkpoint 续跑的可信证据恢复

gpt-6-luna/max。生产实现所有权：Harness checkpoint metadata 常量与 runs/worker.py，Gateway services.py 和固定查询 artifact 能力，Analytics evidence_bridge.py，直接相关测试、模块说明与本切片验收记录。其他源码冻结；不构建、不部署、不调用模型。先读相关 AGENTS 和 `docs/acceptance/2026-10-08-analysis-checkpoint-evidence-audit.md`。

缺陷：新 run collector 仅读取当前 run；显式 checkpoint 恢复旧工具历史后不能复核旧成功 query evidence。实现最小来源恢复，不扩展通用恢复框架，不改数据库 schema，不扫描整线程历史。

1. Harness 每次运行无条件覆盖保留的 checkpoint producer metadata 为服务端 record.run_id；客户端 body.metadata/config.metadata/configurable 同名值不能成为来源。App->Harness 仍单向依赖。命名保持稳定机器标识，中文说明边界。
2. Gateway 的显式 checkpoint selector 读取已经按目标 owner/thread 验证的 tuple，取得该 producer，使用 owner-scoped RunManager.get 并核对 record.thread_id 与 user_id。只为真正显式 checkpoint 续跑发行一个已验证 producer 的 artifact capability；普通新输入不继承。不存在、无效、不同 owner/thread 或未完成 producer 不恢复；旧无字段 checkpoint 仍可继续，但引用旧 evidence 失败关闭。
3. 不直接复用 edit/rerun 的 success-only 校验：中断/失败 run 内已经成功的受控查询也应能从其 checkpoint 恢复。允许已终结 producer（success/error/interrupted 等按实际枚举），拒绝 pending/running；只有成功 query DTO 能恢复，artifact 与摘要始终逐份复核。主会话明确更正 audit 的 success-only 建议。
4. collector 仍 matches 当前 principal/thread/run、新查询写当前 run；解析仅允许 current + 一个已验证 producer，按对应 scope 与原固定 artifact 逐份验证并保持请求顺序、批量整体失败。不得复制旧证据到新 run 冒充新查询。相同 evidence ID 跨来源冲突或出现两份候选时拒绝，缺失/损坏/身份错/文件错拒绝。最多20份/16MiB既有预算保留；不因多来源放宽。仅 producer 可证明来源，更早历史编号 fail closed，重新查询即可。
5. 来源由 admission 局部变量/服务端 capability 传递，不塞可由用户任意改写的 config 当信任根；不添加新的模型工具参数、自由文本事件或不必要公共接口。metadata 自身不含 SQL/结果/凭据。

V2 验证：先写 confirmed-regression（同 owner/thread 显式 checkpoint 恢复原成功 evidence），实现完整切片后跑直接相关节点/模块一次；覆盖客户端伪造、跨 owner/thread、普通新输入不继承、旧无 producer、终结 interrupted 中成功 query、未结束拒绝、跨来源冲突与文件篡改。复用已有 fixture/repo，不重跑既有345或全仓 suite。受影响 Python Ruff check/format、diff；uv 用 --no-config --default-index https://pypi.org/simple --locked --no-sync，uv.lock 不改。记录 actual diff/精确检查与尚未验证的真实PG边界。

若显式 command.resume 没有 selector 不可明确来源，则本切片不猜来源或自动授权历史；记录该限制。实现结束冻结后交主会话独立审查，Gateway build 等此切片通过。
