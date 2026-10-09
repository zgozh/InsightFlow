# AS-01 / AS-15：隔离默认四服务与双主体真实验收

执行者：用户最新指定 `gpt-6-luna` / max。先读根/目标模块AGENTS、完整发布计划的里程碑1、差距报告AS01/15及两场景。主会话已独立复核差距报告：普通task不进入可信分析，现有用户无删除API；因此用户夹具必须建立在全新隔离应用home，不在原29384账号库内注册。

## 独占与依赖

独占新报告 `docs/acceptance/2026-10-07-as01-as15-default-stack.md`、必要PROGRESS/AS矩阵更新、唯一 `.reviews/as01-as15-<uuid>` 临时runner与资源。现有前端diff/两份提示词/固定栈全保留。不改产品代码；明确产品缺陷先报告主会话，随后另派修复。

只读取所需接口，完成有界实际验收，不停在计划。V3为本次两项真实认证/默认部署旅程；不跑所有AS或全仓测试，不发模型请求。约60秒进度。

## 环境准备

1. 只读核对Docker Engine、已有Compose projects/default `deer-flow` 项目、现有固定栈与本轮Frontend/Gateway image。禁止替换/删改原 `insightflow-acceptance-local` 或其他旧项目。
2. 优先在尚不存在的默认 `deer-flow` 项目运行原 `scripts/deploy.sh start`（即make up底层readiness路径的no-build模式），复用镜像但核对源image；环境变量指定唯一应用home/config/extensions、loopback新端口（先核对未占用）和新内部/认证secret。如果默认project已有资源，不触碰，采用唯一新Compose project和**只覆盖名称/镜像/绑定/隔离mount**的最小overlay；明确报告此时对make up readiness的证据来自原脚本定点检查，不把overlay说成原始未经修改启动。
3. 使用原 `docker/docker-compose.yaml` 四服务，不加业务库/AIO/第五服务。每个镜像/容器名/网络/新volume和host path有slice标记，配置文件/应用home仅在 `.reviews` 新子目录内。复制必要已有运行配置并仅在隔离副本启用 `auth.local.allow_registration`、Analytics；secret只在进程/忽略文件、从不输出，不能写真实根config/.env。
4. 保持SQLite默认，`run_events.backend=db`；新栈无真实数据，readiness通过后才报告成功。证明nginx127.0.0.1、Gateway/Redis无宿主发布、恰好四服务、Redis非profile、SQLite存在于已挂载新home。

## 真实认证与合成owner fixture

- 通过真实 `POST /api/v1/auth/initialize` 建临时admin A、`POST /api/v1/auth/register` 建普通B；各用不同真实session/browsercontext登录。账号随机强密码和slice-tag email，私密值不打印、不提交。可以为后续同隔离环境加新DPAPI文件，但不读写原验收管理员凭据。
- 通过正常API建立A/B线程；A analysis thread需真实 `kind=analysis` 和持久marker。为AS01“系统内已存在其他主体thread/run/artifact”建立**明确标记为合成夹具**的run/event/checkpoint/普通文本artifact与datasource授权数据。可从隔离Gateway内部使用已有repository/Paths写入fixture；不得连接真实模型，不得在报告把fixture说成模型产物或业务分析链。优先复用已有测试fixture结构/真实存储接口，不凭猜测直接写数据库字段。
- 未登录浏览器analysis入口应跳登录；受保护thread/run/messages/events/SSE/analytics/artifact API为401且不含fixture数据。
- A读取自身thread/run/messages/events/artifact和有权datasource正常；B访问A的对应对象为404（或契约明确的拒绝状态），返回无A标题/消息/路径/evidence/内容；list/search结果不带A数据。检查SSE join拒绝而非进入长等。B不能调用admin路由；B读取自身对象正常。API与UI都用真实认证，不使用auth-disabled/mock request.state。
- A浏览器通过Nginx登录后进入分析工作台；可看到合法空态/既有安全控制，不发送消息。此证据只用于AS01/15。

## 检查与交付

定点范围：`tests/test_auth_middleware.py`、`test_stateless_runs_owner_isolation.py`、`test_compose_default_bind_host.py`和已有默认服务/readiness脚本测试；只选直接相关测试函数/文件，必要Analytics访问测试。先用 `rg --files` 找当前测试路径，不猜不存在文件名。执行环境沿用已安装backend .venv，不同步升级依赖。对没有生产改动的本切片不跑lint/build/full suite。

报告每条场景条件的真实输入/HTTP/安全布尔/计数、准确命令退出码、镜像/资源标识、初始不存在/新建证明、所有未覆盖项。矩阵只有完整条件已证实才标已验收；不以脚本退出0替代case核对。账号/fixture/session/模型正文一律不写公开报告。

新隔离环境成功后先保留供后续里程碑复用，报告其参数与只包含凭据**路径**的恢复信息，不执行清理。后续最终清理必须只作用于本切片资源；任何递归删除先核对绝对路径处于该唯一目录，用PowerShell原生命令端到端，不跨shell组合删除。

主机若自动审批拒绝生命周期动作，准确报告动作与原始原因，不绕过/换壳重试；继续不依赖该动作的定点验证与文档。返回后主会话独立复核并自动派下一里程碑。禁止commit/push。
