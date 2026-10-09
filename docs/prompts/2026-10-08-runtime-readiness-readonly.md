# 发布集成环境只读预检

用户已恢复完整发布验收。由 `gpt-6-luna` / max 做一个很小的只读预检，供接线切片完成后部署/验收使用。其他两个实施者正在写前端和Gateway，禁止读改它们源码、tests、docs；本切片不执行应用验证。

只检查 Docker Engine 能否连接、两个已存在项目 `insightflow-acceptance-local` 与 `as01-as15-1bf6932f3abd` 的容器服务名/精确ID/状态/health/已发布端口、入口29384和29385的匿名 `/health` HTTP状态。只投影上述安全字段，不输出env/配置/secret/日志正文。不得启动Docker Desktop/容器、restart/recreate/build、全栈up、注册账号、登录、修改卷/真实数据或发模型请求。主机若拒绝只读命令，报告原拒绝，不换手段绕过。

可写唯一忽略证据文件 `.reviews/runtime-readiness-20261008.json`（UTF-8，安全字段），不改其他文件、不追加验收文档，不跑tests。一次预检后返回实际结果与是否阻塞后续运行；环境状态是即时快照，不宣称发布验收通过。完成立即冻结，不扩展诊断。
