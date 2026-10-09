# 手动部署脚本：保持现有三个容器身份

主会话独立读回准备脚本，发现 update/rollback 都以compose up启动Redis、业务PG与Nginx。即使加--no-build/pull never，Compose仍可能因配置hash或可变image tag重建它们，违反“另外三容器ID保持”的已冻结要求。须在交给用户Apply之前修。

原builder当前只构建Frontend，原准备脚本已冻结。本切片由原builder在当前build调用结束后执行，不与镜像build并行编辑任何源/脚本。只拥有 `.reviews/release-deploy-20261008/{update-fixed-stack.ps1,rollback-fixed-stack.ps1}` 与其原验收记录。禁止实际Apply/start/restart/up，禁止新backup/恢复或重跑app tests。

1. 对Redis、analytics-demo-postgresql、Nginx，改用经fixed project/service标签校验后的beforeMap精确Container.Id执行 `docker container start ID`（手动Apply分支），不能Compose up这三服务。保留健康等待、原Nginx等Gateway就绪后再start的顺序，使DNS解析新Gateway。Gateway/Frontend仍为受限compose up --no-deps --no-build --pull never，仅这两服务可替换。
2. Update完成应以真实homepage HTTP200和Nginx转发的`/health` HTTP200作最终确认；设置一个小且有界的startup重试窗口防Nginx刚启动瞬间false failure，失败继续脱敏、不能先打印complete。不要重新设计一套监控系统。
3. 回滚既有explicit DataLoss acknowledgment/停writer/SQLite完整备份恢复逻辑保持；这里只将不允许替换的三服务start改精确ID。不在Agent工具里触发其中任何写DB/启动分支。
4. PowerShell语法、默认plan/dry-run和safe diff readback验证即可。不得运行Apply、全栈up或真实rollback。报告改动与实际只读检查结果，冻结。
