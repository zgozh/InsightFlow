# 发布后修复部署

主会话已独立审查导航和 Lead 提示词补正，接受源码与定点证据。实施者 gpt-6-luna/max。

1. 基于当前已运行 Gateway 镜像增量 COPY 唯一修改的 prompt.py，不重装依赖；前端用已安装依赖生产构建，将实际构建产物打入新镜像。复用已有构建脚本/镜像，不创建新服务栈，不升级锁文件或依赖。
2. 仅更新 insightflow-acceptance-local 的 Gateway/Frontend，保留 Nginx、Redis、业务 PostgreSQL 容器与全部配置、账号、聊天数据和卷；保持127.0.0.1:29384入口。记录旧镜像以便回滚。历史 rollout.ps1 固定旧容器ID，不直接运行；按当前ID/挂载/端口做必要核对，Compose --no-deps --no-build --pull never 仅指定两个服务。原用户已授权部署，无需再问。
3. V3限于本次部署：健康/ready/首页、实际运行Gateway prompt构造确认InsightFlow无旧品牌、浏览器新聊天/历史聊天/分析列表/新分析选中互斥。不发付费模型请求；复用已有安全浏览器登录流程，不输出登录凭据或聊天正文。没有可复用浏览器登录时如实报告，不创建/重置账号。
4. 记录实际构建/部署/check命令退出码、安全版本/镜像/健康状态、源文件hash。新增一份简短中文 docs/acceptance 发布后修复证据；必要更新PROGRESS和INTERRUPTION的当前状态，历史证据不改写。不声称这轮重新跑全部AS验收。
5. 冻结后返回实际diff/精确检查结果供主会话审查，暂不commit/push。保护canonical uv.lock SHA256=46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912。不读取输出秘密，不全量Docker inspect输出。

## 独立审查与提交授权

主会话已审查实际源码 diff、路由矩阵和部署记录，并独立读取原入口三个 HTTP 200、容器 prompt.py SHA256 与 BUILD_ID，均匹配。接受登录后浏览器矩阵未执行的明确限制。

按用户既有授权正常 commit 并 push origin main，仅纳入本次九个变更文件，正常运行 hooks，不跳过门禁。使用作用域内 UV_NO_CONFIG=true、UV_DEFAULT_INDEX=https://pypi.org/simple、UV_NO_SYNC=true，执行后恢复；保护锁文件哈希。Hooks 若有实际修改先返回 diff，不擅自扩大修复。提交后核对本地/远程 HEAD 和干净工作区。不重复测试、构建或模型请求，不创建标签/PR；远程 CI 未查则如实报告未核验。
