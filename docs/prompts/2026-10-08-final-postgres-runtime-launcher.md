# 最终 PostgreSQL 验收环境启动材料

gpt-6-luna/max。本切片只拥有 `.reviews/final-postgres-runtime-20261008/` 下的新启动脚本与安全输出，以及 `docs/acceptance/2026-10-08-final-postgres-runtime-launcher.md`。与 checkpoint 源码只读审查独立；不得修改生产源码、旧 fixture TLS 证据、已有容器、29384/29385、MySQL。

你的前一切片已完成测试 PG 的 TLS、专用 app role、四服务 runtime.compose.yaml 和静态预检。现需把 prose 操作材料变成可执行启动入口，供新镜像冻结后用。当前 Frontend 新 ID 为 sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c；最终 Gateway 未构建，禁止拿旧 51c0 镜像当新版部署。

创建一个最小 PowerShell 启动脚本：显式必填 Gateway/Frontend immutable image IDs，Redis/Nginx 参数沿用已有预检机制；所有 image IDs 需本地可用、pull_policy never、无 build。仅固定新 project iflow-final-pg-20261008，唯一 published loopback 29388，独立 app-home/Redis，Gateway 接外部 PG fixture network。复用 runtime_preflight.ps1 与已暂存 env-ref config，秘密只 DPAPI CurrentUser 解密进子进程 env/stdin，finally 清除；不输出密码、DSN、真实 config、完整 compose 渲染、原生异常正文。不能将主项目环境变量改写持久化。

默认只预检，显式 -Apply 才 compose up 新项目。若发现新项目已存在或端口占用，检查已知身份并停止/报告，不能覆盖未知资源。准备好后本切片不执行 Apply。不要追加宽泛自动回滚/恢复框架；失败输出稳定 stage/code 与允许的健康状态即可，原生日志留本目录不对话打印。Gateway 使用 PostgreSQL extra 必须在镜像构建时具备，若参数镜像缺依赖预检报告即可。

验证 V0/V1：PowerShell AST 与已存在预检静态允许字段；若没有最终 Gateway ID，明确待传入，不使用旧 ID 假装最终通过。不启动 Docker Desktop、容器或模型。冻结实际文件、用法、检查结果与仍待真实执行的门禁。
