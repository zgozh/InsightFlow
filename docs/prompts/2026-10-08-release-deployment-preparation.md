# 指标授权与耐久证据：可审阅部署准备

用户已恢复完整发布验收，主会话已独立接受metric后端权限与bridge源码边界；前端生产也已独立审查，剩余仅2文件测试夹具修补。原固定 `insightflow-acceptance-local` 五容器全部exited，29384不可达；隔离 `as01-as15-1bf6932f3abd` 四容器健康，29385/health200。先前主机自动审批拒绝原Gateway/Frontend/Nginx启动，**不得在Agent工具里启动/重建/重启任何现有容器**。

本任务 `gpt-6-luna` / max，仅拥有 `.reviews/release-deploy-20261008/` 忽略目录和独立验收记录 `docs/acceptance/2026-10-08-release-deployment-preparation.md`。不改任何源码/tests/根docker文件/真实账号/现有卷。不要派其他Agent。不打印真实env、rendered compose JSON、DSN/密钥/用户数据。

## 首段：准备，不构建/部署

当前其他Agent在改frontend tests和backend注释，因此先准备独立脚本与safe manifest，**收到主会话明确源码/测试冻结消息后才build images**。不启动容器。

1. 复用 `.reviews/phase-06f3f21-deploy.ps1` 的固定compose project、env-file组合、analytics-demo overlays和fixed override，不原样执行（旧脚本要求running，且会up）。读现有固定stack labels/精确container IDs、三个卷与当前image IDs；当前不running是预期。本任务仅inspect/create准备文件，不改变容器。
2. Composerendered JSON仅在内存/管道由Python检查器读取，stdout只有safe字段/布尔结果，不输出environment值。确定Frontend/Gateway有效配置与当前旧容器一致，除了后续image变化；入口Nginx维持既有127.0.0.1:29384映射，不受根PORT=2027漂移影响。不得full-stack up。
3. 给旧Frontend/Gateway image分别保存明确rollback tag（仅镜像tag，不启动服务）。此前品牌tag保留，不覆盖。检查新源码0003/0004会推进Analytics Alembic，**旧image不认识新revision，单独回滚image可能拒绝启动**；所以准备人工更新脚本时，在当前Gateway已stopped且确认该卷无其他running writer的情况下，把原SQLite app DB及存在的WAL/SHM一致复制到忽略backup目录，不读取内容、不打印rows。如当前实际应用DB不是SQLite先报告，不能假定备份完成；不在Agent工具里恢复DB或做真实升级。
4. 编写人类可审阅的 PowerShell 更新脚本（默认只plan；须显式 Apply才运行）。所有路径Literal/固定，失败检查LASTEXITCODE；本任务不得运行Apply。Apply只启动原Redis/业务PG，等健康；使用既有compose只替换Gateway/Frontend `up -d --no-deps --no-build --pull never gateway frontend`；确认Gateway readiness后启动原Nginx，使DNS解析新Gateway。校验另三容器ID/三卷/29384映射保持，health/ready和首页实际成功后才打印完成；失败仅显示安全状态和有限脱敏原因，不dump config/env/secret/raw日志。不删除卷、不改变数据策略/账号、不重新初始化admin。
5. 准备回滚说明：暂停app writers后才能恢复一致SQLite备份并用旧image；备份之后的新记录会丢失，写清这一具体限制。可准备默认dry-run回滚脚本，但不得运行。不要构造跨shell delete/move，禁止recursive delete。

## 第二段：主会话发冻结消息后

仅build新Frontend/Gateway镜像，不start/up/recreate；使用现有compose build，输出保持小且不泄密。build是发布边界V3必要检查，不另机械pnpm build重复同一个编译。源码包/lockfile不得为build方便改写或重新生成，使用固定版本；遇到真实失败先报告原因和最小相关修复，不循环重跑同命令。

完成记录新image IDs/tag、旧rollback IDs、safe config/port/volume校验结果、SQLite备份文件安全路径及执行状态。报告清楚“已构建/脚本可审阅，尚未部署”，给用户一条可直接运行的更新命令（因为既往host review拒绝了自动启动），然后冻结交主会话。所有app/model/业务SQL真实验收留下一slice，不注册用户、不调用模型。
