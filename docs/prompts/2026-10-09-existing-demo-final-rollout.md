# 原演示入口最终升级准备

gpt-6-luna/max。用户已授权项目完整交付，原29384五容器保留，最新源码/image仅在29388验收，不能把原用户入口误称已更新。本切片先做**只读准备，不Apply**，Root独立review后执行。

独立所有权 `.reviews/final-postgres-runtime-20261008/original-entry-rollout/` 与 docs/acceptance/2026-10-09-original-entry-final-rollout.md。其它worker正在doc/tests，不共享写文件。生产源码/原凭据/权限不修改，无模型、不启动新栈/新容器组、不删除卷/旧data。

只读原project insightflow-acceptance-local 五容器原名/ID/image/state，exactpublishednginx29384、volumes/mounts/compose config_files label，project不与其它deer-flow/docker混淆；Gateway/Front当前旧source。最新验收images Gateway1109d361…与Frontend365f5538…完整hash直接read，持有旧rollbacktags（如果oldimages缺失必须先准确说明）。原appdatabase SQLite或PG实际 config只安全解析backend与路径，不打印envDSN。识别原应用DB备份正确机制，PG pg_dump或SQLite文件copy需停Gateway一致性，原配置/认证/secretref从原容器/host材料以内存复用，不向新的29388复制用户账户，原用户权限保持。

准备一个PS5兼容reviewable脚本，default inspect/preflight，显式Apply才更新；精确项目ID/ports/mountsourcefile/type守卫，只替换原Gateway/Frontend镜像，后台仍原PG/Redis/Nginx，不迁移端口/重建数据；有app数据备份/旧image rollbackguard，启动后真正health/readiness/default401、Frontend首页与版本，数据库迁移状态用revision不要打印rows。wrapper EAPContinue+LASTEXITCODE，authsecret不换；Dockercompose不能把containerpath用作hostsource。

原启动以前曾host自动审批拒绝且用户手动恢复；当前新授权“重新打开然后测试”、dangerfullaccess存在，但你此slice不执行启动/Apply，由Root综合确认安全权限后按已授权范围推进；不要绕过新的审批拒绝，任何block准确交。

先交preflight安全摘要+脚本路径/ASTcheck+备份/恢复最短计划，冻结，避免原入口增加新模型测试/全suite。不写已升级或已完成，尚pendingApply。
