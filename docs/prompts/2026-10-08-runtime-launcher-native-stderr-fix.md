# 启动器原生 stderr 定点修正

gpt-6-luna/max。只改 `.reviews/final-postgres-runtime-20261008/launch_final_postgres_runtime.ps1` 的 Invoke-Docker 及本切片验收记录，其他所有文件不动，不 Apply，不操作现有项目。

主会话审查确认：全局 ErrorActionPreference=Stop 下 `& docker @Arguments 2>&1` 在 Windows PowerShell 5.1 可因正常原生 stderr 触发 terminating error；而资源守卫依赖 volume/network inspect 缺失时的退出码。这正是前次部署 helper 已遇到的问题。最小修正 wrapper：本地 scope 对原生命令 stderr 使用非终止捕获，保存真实 LASTEXITCODE，finally 恢复，不把 stderr 直接打印、不忽略非零退出。可用局部 ErrorActionPreference=Continue 包围现有数组捕获；不添加整套 process 框架。

验证 PowerShell AST，再一次无副作用的直接 wrapper 探针：docker volume inspect 一个确认不存在的专属随机名称（不得 create/delete），预期返回非零+捕获内容而不跳外层 catch；只输出探针布尔/exit code，不打印原生日志。还需成功 docker version/info 返回0。入口本身不执行，保持无 -Apply。冻结记录修正diff和精确检查。
