# Phase 6F3E7 Fix 02：复用已初始化管理员并按真实角色契约继续

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e7-fix-01-valid-acceptance-email.md` 与原 6F3E7 提示词。此处是忽略目录中验收 runner 的两处假设修正，不是产品缺陷；保留固定栈和现有 DPAPI 凭据。

## 已证实的问题

同一固定栈已 `initialize=201`、`login=200`、`GET /api/v1/auth/me=200`；runner `.reviews/phase-06f3e7-run.py` 却读取不存在的 `principal['is_admin']`，产生假阴性。`backend/app/gateway/routers/auth.py::get_me` 明确返回 `system_role=user.system_role`。runner 当前又在 `needs_setup=false` 时提前返回，无法复用刚创建的管理员。

## 最小改动与继续执行

1. 只修改被忽略的 `.reviews/phase-06f3e7-run.py`：`needs_setup is True` 才调用 initialize；`needs_setup is False` 跳过 initialize、直接 login；其他类型/缺字段 fail closed。`/me` 必须要求非空 id 且 `system_role == 'admin'`，不再读取不存在的 `is_admin`；只输出 role-match 布尔值，不输出邮箱/凭据/权限明细。保持其他请求、CSRF 和安全输出规则不变。
2. 先做脚本 AST/语法与上述两个局部分支的最小离线校验；不造新通用客户端，不跑全量套件。确认现有 DPAPI 文件仍在、只可由当前用户解密，**不删除、不轮换、不重新初始化账号**。固定 `insightflow-acceptance-local` 保留现有容器/卷，旧 6F1 不动（其当前 5 个容器已退出，这是外部状态，不要恢复或清理）。
3. 复用同一加密凭据运行修正后的 runner，按原 6F3E7 顺序继续 login→principal→CSRF→合成 datasource/schema/policy→analysis thread→**最多一次**真实 `deepseek-flash` run。工具稳定码只从 `Content-Location` 对应的 run-messages API 获取；Reviewer 失败取同 run 安全 stage。遇到下一处真实错误，仅记录安全状态/阶段并停止，不重试模型或擅自修改产品。

## 交付

写 `.reviews/phase-06f3e7-fix-02-existing-admin-role-contract.md`，记录两处脚本修正、离线检查、业务阶段、run 数与两项目资源状态；不泄露 email、密码、Cookie、SQL、结果行、报告正文或模型文本。跟踪工作树干净，不提交 `.reviews`；本轮不改产品代码/依赖，不跑全套测试或 E2E。完成停在主会话复验。
