# 复用现有 Gateway 运行环境、补 PostgreSQL extra 并启动验收环境

gpt-6-luna/max。前置事实：常规 Gateway 构建因 Debian apt 源502失败，未进入Python安装、无新镜像、无Apply。旧51c0镜像已离线import确认asyncpg0.31.0/redis7.4.0/langgraph1.2.9及Node/npm/uv可用；缺psycopg/psycopg-pool/langgraph-checkpoint-postgres。其pyproject/uv.lock与当前冻结源码完全相同。这支持复用旧运行环境，只补已锁定postgres extra。此任务在主会话审查冻结事实后执行。

所有权：`.reviews/release-stage-build-20261008/gateway-build-20261009/` 的派生构建材料/结果，`.reviews/final-postgres-runtime-20261008/` 的启动结果/安全探针，`docs/acceptance/2026-10-09-gateway-reuse-runtime-startup.md`。不改正式Dockerfile、生产源码、pyproject或uv.lock；不触碰29384/29385/MySQL容器和真实账号，不发模型。

1. 基础镜像固定已检查 sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716。可用它的现有本地tag作FROM，但构建前后核对该tag的image ID均等于此ID，禁pull；不得无条件覆盖旧tag。新image使用独立 `insightflow-release-gateway:pg-20261009`，先确认不存在。派生Dockerfile仅放ignored目录。
2. 复用已冻结Backend-only context。保留基础镜像 `/app/backend/.venv`、Node/npm/uv/Linux运行环境；在镜像内部移除 `/app/backend` 的旧源码项（只保留 `.venv`，例如find固定绝对目录的一层条目），再COPY当前backend，避免删掉的旧模块残留。不移动/重复制整个.venv，不触碰主机文件。真实.env/config/.deer-flow/运行数据不能进入COPY；root.dockerignore保持原规则。
3. 同镜像中仅执行一次 `uv --no-config sync --locked --default-index https://pypi.org/simple --extra redis --extra postgres`，复用已安装依赖与uv cache；不执行apt/npm/Node重装，不改registry配置，不使用未锁定pip install。PG extra含psycopg[binary]已在锁中，优先wheel，无需编译器。若PyPI网络失败，报告具体稳定阶段/安全错误，不盲目改锁或镜像源。
4. 保持原Gateway入口/工作目录一致，最终镜像确认离线import缺失三个包和PostgresSaver/Redis成功，输出限定版本；核对uv.lock SHA46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912，以及冻结关键 services.py/worker.py/stages.py/roles.py 源码摘要与镜像文件一致。记录immutable imageID和build退出码。这是改变构建策略后的针对性重试，原502不重复跑。
5. 成功后依照已授权 `docs/prompts/2026-10-09-gateway-build-postgres-startup.md` 的第2/3步，传新GatewayID与Frontend fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c 给 launcher：默认预检后 -Apply，只启动新 iflow-final-pg-20261008 / loopback29388。验证四服务/健康/镜像ID/专用应用PG迁移与checkpointer表、业务PG verify_full + SELECT-only 3行。用户继续任务已授权，无需再次确认；若主机拒绝则报告，不绕过。无模型/seed/grants/调度/恢复/原入口替换。

V3仅发布构建/依赖与启动门禁；保留既有source和fixture证据，不重跑应用suite/前端build。对长build保留原session+可见exit code、专属log，不丢失输出后重复build。敏感值DPAPI进程env/stdin，finally清除；只输出safe count/revision/hash/status，不DSN/凭据/SQL结果/完整compose或环境。

冻结实际diff/命令、依赖表、imageID和真实启动结果。若启动故障，做窄环境定位，生产缺陷交回主会话，不跨所有权修复，不删除卷/数据。
