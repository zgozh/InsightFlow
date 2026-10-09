# 手动部署部分成功后的 PowerShell 误报与路径修补

用户已实际运行update-fixed-stack.ps1 -Apply，输出 update_failed/stage=replace_gateway_frontend。主会话只读核对发现两个新应用容器已正确运行，Gateway healthy，PG/Redis healthy，Nginx仍旧exited。新Gateway ID0e79879e8ce0ab1c16c6c8dd6b106588d288b396e489146f0770ec7c046d0181/image51c0cc1...，Frontend86e254ed.../imagea45a6dd...；原另外三ID与三卷/loopback29384保持。

已指导用户仅手动 `docker start insightflow-acceptance-local-nginx-1` 补最后一步，不重新Apply。**你不能在工具里start/up/recreate/restart任何容器或执行Apply/rollback**，原栈启动仍受既往host review拒绝约束。

`gpt-6-luna` / max只拥有 `.reviews/release-deploy-20261008/` 中相关helper/update/rollback文字与 `docs/acceptance/2026-10-08-release-deployment-preparation.md` 补记。严禁改repo生产源/锁/tests/账号/真实DB，不读打印raw env/log/SQL/行，不派Agent。

## 已定位疑点与最小检查

1. update/rollback的Invoke Compose函数在 `$ErrorActionPreference='Stop'` 下 `& docker compose ... *> $null`。Compose成功进度输出stderr可能在Windows PowerShell被抛成NativeCommandError，而应用替换实际成功。先用一个无副作用的Python程序“写ASCII stderr并exit0”，在同一PowerShell设置/重定向下复现，记录PS版本/是否throw/实际exitCode；**不要用真正Compose up复现**。如能确认，采用最小临时ErrorActionPreference作用域（恢复原值，并依实际LASTEXITCODE判成功/失败）或已有安全subprocess capture，使成功stderr不成为错误，非零码仍失败。不要用放宽真实exitCode的Ignore包裹；不要输出秘密。用exit0-stderr与exit非零两个合成case验证。
2. safe_manifest.py用容器config bind Source直接当WindowsPath。新容器inspect source为 `/run/desktop/mnt/host/d/develop/workspace/InsightFlow/.analytics-demo/config.yaml`，因此误报 unverified_config_missing；旧容器Source原是D盘路径且preflight曾通过。只对已知Docker Desktop前缀按drive映射原生路径，验证resolve落在本workspace，目标仍固定 /app/backend/config.yaml，不接受任意别的前缀/逃逸。当前实际配置仍SQLite，Gateway健康；不能把helper路径误读当实际配置丢失。
3. 记录真实“替换已成功、脚本未完成入口恢复”的状态、更新后的精确ID/image与Nginx未启动边界。旧script仍是本次one-shot first-deploy，当前已部分更新，不要为了让defaultplan通过而放宽其oldimage/全stopped前置条件，也不要重复执行。无需设计新的resume平台；用户单步启动Nginx后主会话验收。
4. 对改动helper的Python AST/PowerShell syntax及上述两合成stderr case，safe_manifest只读配置判定，V0/V1局部验证足够；不跑应用tests/镜像build/重备份真实DB。最多修必要的两个InvokeCompose函数及path映射，禁止扩大脚本功能。

报告精确根因证明、实际diff/命令/退出码和不能重放first-Apply的状态限制，冻结。若合成case不支持推断，记录未确认并只加安全exitCode可观察性，不捏造stderr根因。
