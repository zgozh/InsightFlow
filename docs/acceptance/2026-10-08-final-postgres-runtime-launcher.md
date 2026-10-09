# 最终 PostgreSQL runtime 启动器准备记录

本切片新增独立入口 [launch_final_postgres_runtime.ps1](../../.reviews/final-postgres-runtime-20261008/launch_final_postgres_runtime.ps1)，目标仅为固定项目 `iflow-final-pg-20261008`。入口要求显式传入 Gateway、Frontend、Redis、Nginx 的 `sha256:` immutable image ID；Gateway/Frontend 不设默认值，旧 Gateway ID `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716` 会被拒绝。当前已知 Frontend ID 为 `sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c`；Redis 和 Nginx ID 沿用上一切片记录。最终 Gateway image 尚未构建，待后续传入。

默认运行只执行入口内的镜像/资源守卫、PostgreSQL extra 探针和既有 `runtime_preflight.ps1`；只有显式带 `-Apply` 才会对该新项目执行 `docker compose up -d --no-build --pull=never`。目标发布端口固定为 `127.0.0.1:29388`，Gateway 使用独立 app-home/Redis 并连接既有 PG fixture 网络。入口检查固定项目资源和端口碰撞，遇到已有资源即停止，不覆盖未知资源。凭据从现有 DPAPI CurrentUser 文件短暂解密到当前进程环境变量，退出时恢复原环境变量；结果只写稳定状态码、阶段和健康摘要，原生命令输出留在本目录的日志文件中。

调用形式如下；Gateway ID 必须等最终镜像冻结后补入：

```powershell
.\.reviews\final-postgres-runtime-20261008\launch_final_postgres_runtime.ps1 `
  -GatewayImageId 'sha256:<final-gateway-id>' `
  -FrontendImageId 'sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c' `
  -RedisImageId 'sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf' `
  -NginxImageId 'sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752'
```

本次仅以 PowerShell Parser 对启动器做 AST 静态解析，结果通过。没有运行入口、既有预检或 `-Apply`，没有启动 Docker Desktop、容器或模型；因此这不是服务启动或端到端验收结果。真实执行仍待最终 Gateway image ID 冻结并由主会话统一安排。

## 原生 stderr 捕获定点修正（2026-10-09）

`Invoke-Docker` 现在只在原生命令捕获期间把局部 `$ErrorActionPreference` 设为 `Continue`，并在 `finally` 恢复调用方值；退出码仍读取 `$LASTEXITCODE`，捕获内容继续交给原日志函数，不直接打印。PowerShell AST 检查通过。随后从脚本 AST 单独取出并调用该 wrapper，未执行启动器入口：对随机专属且确认不存在的 Docker volume 执行只读 `inspect`，结果为不跳外层 catch、捕获 stderr、确认 `no such volume` 且退出码为 `1`；`ErrorActionPreference` 恢复为 `Stop`；`docker version` 与 `docker info` 均未抛错且退出码为 `0`。探针仅输出布尔值和退出码，没有输出原生日志，也没有创建或删除资源。

本修正未运行 Compose 预检或 `-Apply`，未启动应用容器或模型；实际运行验收仍待最终 Gateway image ID 冻结并由主会话安排。
