# Phase 6F3E7 Fix 01：修正合成管理员邮箱并继续唯一分析 run

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e7-persistent-stack-single-analysis-run.md` 和原提示词 `docs/prompts/phase-06f3e7-persistent-stack-single-analysis-run.md`。本文件只覆盖邮箱输入及因此必须轮换的**尚未使用** DPAPI 临时凭据；其余安全/单 run/持久栈边界保持原样。

## 已确认根因

初始化唯一失败为 `422 body.email:value_error`。无凭据脚本 `.reviews/phase-06f3e7-run.ps1:29` 生成 `acceptance-<uuid>@example.test`；Gateway `InitializeAdminRequest.email` 是 `EmailStr`，仓库既有认证测试使用 `@example.com`。项目 `insightflow-acceptance-local` 的真实 setup-status 仍为 `needs_setup=true`，所以没有管理员需要迁移。

## 最小修复与验证

1. 在脚本中只把合成邮箱域名 `example.test` 改为 `example.com`；不要改产品邮箱验证或 API。用后端现有环境对同形状、非私密邮箱运行一次 `TypeAdapter(EmailStr)` 或等价离线校验，确认新值合法；无需全套 pytest。
2. 再次确认固定验收栈的 `setup-status` 为 `200 needs_setup=true`，并确认旧密文文件精确路径为 `.reviews/insightflow-acceptance-local.admin.dpapi`、仍处于被忽略目录且没有成功账号引用它。然后**仅删除这一个未使用的 DPAPI 密文文件**，由修正后的脚本重新生成随机密码/邮箱并以当前用户 DPAPI+独占 ACL 保存；删除与重新生成均不输出明文。若任一前置事实不成立，停止，不删文件、不写账号。
3. 复用同一固定 Compose project、端口、现有 httpx 客户端和 DPAPI 脚本，重做一次初始化。成功后按原 6F3E7 继续 login/CSRF、合成 datasource/schema/policy、analysis thread 与**最多一次**真实 `deepseek-flash` run。`Content-Location` 取 run ID，工具结果读现成 run-messages API；Reviewer 失败按同 run ID 取固定 stage。不得重建/销毁栈、不得重试模型；若有下一个明确失败，记录安全状态/类别后停线，不自行扩大产品修复。

## 交付

在 `.reviews/phase-06f3e7-fix-01-valid-acceptance-email.md` 写脱敏结果：离线邮箱校验、旧密文精确替换、初始化与后续各阶段状态、模型 run 数、固定栈和旧 6F1 状态。保持 `.reviews` 忽略、跟踪树干净；不提交产品实现，不跑全量测试/构建/E2E。停在主会话复验。
