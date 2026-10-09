# 新 Gateway 构建与独立 PostgreSQL 环境启动

实施者 gpt-6-luna/max。此任务只能在主会话明确完成 checkpoint 修补独立审查后执行。所有权为 `.reviews/release-stage-build-20261008/` 下 Gateway 专用构建输出、`.reviews/final-postgres-runtime-20261008/` 启动结果与本切片探针，以及 `docs/acceptance/2026-10-09-gateway-build-postgres-startup.md`。不修改生产源码、锁、旧验收证据。不要自行派子 Agent。

已冻结 Frontend image ID：sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c。Frontend 只需复用，不重建。Gateway 旧 51c0 镜像没有最新角色/阶段/续跑，不能当新版。

读取 backend/Dockerfile、根 .dockerignore、既有 runtime.compose.yaml 与 launch_final_postgres_runtime.ps1、runtime_preflight.ps1，以及前一切片启动器验收记录。不要输出或读取展示 .env、config、凭据正文。专用 PG 已启用 TLS，并有 app owner、SELECT-only business reader、独立 app DB 和三个合成业务行；资料在既有 final-postgres-runtime 记录，秘密为 DPAPI CurrentUser。

1. 一次构建新的独立 tag `insightflow-release-gateway:stage-20261009`，先确认不覆盖未知已有 tag。沿用 backend/Dockerfile 最终 production stage，传 UV_EXTRAS=postgres，其他 build args 使用默认、PyPI canonical。冻结 backend 源码建立 Backend-only context 时排除 .env*、真实 config、.reviews、.deer-flow、.venv 和其他运行数据，根 .dockerignore 保持原样；不触碰 global registry。uv.lock canonical SHA256 为 46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912，检查不漂移。不要另跑一次 uv sync/build/test 又重复 Docker build。
2. 成功后记录 immutable image ID、tag、退出码与专属日志。安全读取已有服务 Nginx/Redis image IDs（docker inspect 仅 .Image），不读取 Env。新前端 ID 与此新 Gateway ID 作为启动器显式参数。先运行默认预检，再显式 -Apply 仅启动新 `iflow-final-pg-20261008` 项目；用户完整验收已经授权，不需询问再次启动。若主机自动审查拒绝操作，报告被拒动作与理由，不绕过；原29384/29385与MySQL不得手动 start/stop/recreate。
3. 验证新29388 /health 与首页、四服务健康、唯一 published loopback端口、容器 .Image 与传入ID一致；确认业务PG fixture仍有3行/SELECT-only、应用 migrations 和 checkpoint tables 在专用 PG app DB，而非误落 SQLite。只输出表名/revision/count/布尔等安全字段，不打印 DSN/SQL/结果/密码/完整日志。新项目Gateway=>postgres实际network连接应可用；业务 verify_full 需用现有 CA/reader解析路径验证，失败准确归因。

V3仅发布构建/启动与迁移依赖检查：复用已有 source/fixture 通过证据，不重跑345或前端suite。此切片不调用真实模型，不创建实际用户的 grants，不执行调度/恢复/原入口发布。模型及最终业务验收留下一切片。失败先定位具体环境/配置/源码原因，不改源码越权；稳定code+safe摘要并交回。预检通过但实际启动失败不算成功，保留资源以便审查，不自动删卷或数据。

每次 functions.exec 需 text(result.output)，明确 exit_code/session_id；长构建正确等待原 session，日志可重定向专属路径，禁止丢失结果后盲目重复构建。最终返回实际diff/命令/checks、不可变镜像IDs、新项目状态与尚未完成边界。
