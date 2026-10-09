# 用现有镜像依赖继续恢复实验

gpt-6-luna/max。主会话独立读retryhelper/错误，失败是host venv缺langgraph-checkpoint-postgres；镜像内早已具备，**不安装host新依赖，不重新创建DB**。现有独立DB已迁移，不存在run，继续复用。

优先把现有恢复helper及本切片独立config/path放入已有Gateway的 `/tmp/iflow-unfinished-20261009/`，用 `/app/backend/.venv/bin/python`、工作目录/app/backend、PYTHONPATH=.:packages/harness:packages/extension-api:tests，只连接已授权独立DB（容器host改为postgres5432，密码DPAPI仅stdin/内存，不环境dump、不命令行密码）。现有image已带tests/FakeAgent和postgresdeps，脚本运输用文件/stdin，不node -e或安装。

helper1是真实lifespan+FakeAgent worker进入running后写本slice handoff（安全counts/PID/hash原IDs私有），再精确终止自己helper进程；独立helper2相同配置执行生产startup recovery，核对error/interrupted/orphan_recovered、receipt/线程idle/error正确，严禁杀Gateway主worker或全局恢复真实DB。

当前Reviewerworker计划稍后更新Gateway容器，会导致你的helper丢失。通知他你先占现有容器执行，完成冻结再更新；这不是两个任务能同时写Docker的情况，必须串行容器变更。你的所有权unfinished-recovery/tmp该slice/独立DB，无service变更。

已有需要的fixture/path不要从头重写helper；只运输路径/confighost修复。完成proof/自己DBrolecleanup短记录冻结。如果镜像tests缺失只拷直接fixture文件，不全repo、不装依赖。所有密码stdin到python内存、不得输出完整config/DSN/log。
