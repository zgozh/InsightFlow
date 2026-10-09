# 指标显式授权真实路径验收

## 边界与部署

本次仅使用隔离项目 `as01-as15-1bf6932f3abd` 的既有测试管理员 A 与普通用户 B，入口为 `127.0.0.1:29385`。没有操作 `29384` 原栈或真实账号权限，没有访问经营数据、调用模型、删除账号/线程/证据，也没有修改生产源码。

更新前的只读 Compose 摘要确认项目恰有 `frontend`、`gateway`、`nginx`、`redis` 四个服务；入口只绑定 `127.0.0.1:29385`，Gateway 和 Redis 没有发布端口。Gateway 配置、SQLite home 和 Redis 数据卷均属于该隔离项目；仓库 `skills` 与 Nginx 配置为只读挂载。Frontend 与 Gateway 使用本机已构建镜像 SHA `a45a6dd1a8213a42d5406d3f5f04dfe7042addf11dca0255c8645cc0ae47bce2` 和 `51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716`，`pull_policy=never`，未构建或拉取镜像。

使用的实际命令与退出码：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '.reviews/metric-grants-live-20261008/deploy.ps1' -Action check
# exit 0

powershell -NoProfile -ExecutionPolicy Bypass -File '.reviews/metric-grants-live-20261008/deploy.ps1' -Action update
# exit 0

node --check '.reviews/metric-grants-live-20261008/metric_grants_probe.cjs'
# exit 0

powershell -NoProfile -ExecutionPolicy Bypass -File '.reviews/metric-grants-live-20261008/run-probe.ps1'
# exit 0
```

部署只重建了隔离 Gateway 与 Frontend，并重启同项目 Nginx 刷新 DNS。完成后四个隔离容器均运行，Gateway 为 healthy；运行镜像 SHA 与要求完全一致。PowerShell 部署器与探针启动器均立即读取原生命令的 `$LASTEXITCODE`。

## 授权矩阵与结果

探针为指标 `synthetic_metric_grant_6d0090c3a8644a488ed66b4e3b2965ef` 创建了常量表达式 `1` 的合成定义，不执行表达式。

| 身份与动作 | 结果 |
| --- | --- |
| A 登录并创建 ACTIVE 指标 | HTTP 200；初始状态为 `active` |
| B 首次读取普通指标目录 | HTTP 200；API 与指标页面均不可见 |
| B 读取 admin grants | HTTP 403 |
| 匿名读取 admin grants | HTTP 401 |
| A 在管理 UI 授予 B | UI 发出的真实 PUT 返回 HTTP 200；管理按钮对 A 可见 |
| B 获授权后读取与刷新页面 | API HTTP 200，合成指标可见；刷新页面后仍可见，B 界面没有管理按钮 |
| B 普通指标响应字段 | 与管理指标定义字段集合一致：`key`、`name`、`description`、`expression`、`dimensions`、`version`、`status`；授权前后指标定义未变，也没有增加授权字段 |
| B 数据源授权目录 | 授权前、授予后、撤销后均 HTTP 200；三次响应一致，均为 0 项 |
| A 在管理 UI 撤销 B | UI 发出的真实 DELETE 返回 HTTP 200；B API 与刷新后的页面均不再显示指标 |
| 清理合成指标 | 仅将本次指标置为 `retired`，HTTP 200；没有删除数据 |

外管理员场景未运行：隔离 fixture 中没有可复用的第三个管理员账号，本次没有创建账号。真实 `29384` 账号未被自动授权；本次唯一授权对象是隔离项目中已有的测试用户 B。

首轮探针到达管理 UI 授权并生成截图后，在探针自身的资源关闭代码中误将 Playwright `BrowserContext` 当作 API 请求上下文调用 `dispose()`。该次结果未计入验收；修复关闭逻辑后，以上矩阵由一次完整探针运行通过，退出码为 0。这是探针清理错误，不是产品失败。

## 证据

- 机器可读状态矩阵：`.reviews/metric-grants-live-20261008/api-evidence.json`
- 管理授权面板截图：`.reviews/metric-grants-live-20261008/admin-grant-panel.png`。截图只显示合成指标、隔离测试 principal ID 和授权面板，没有账号名或邮箱。
- 隔离镜像 overlay 与部署命令：`.reviews/metric-grants-live-20261008/compose.overlay.yaml`、`.reviews/metric-grants-live-20261008/deploy.ps1`
- 凭据只在 PowerShell 进程中通过 DPAPI 解密，并经 stdin 传给探针；未写入环境变量、命令参数或证据文件。探针只记录状态、字段检查和合成指标键，不保存响应正文、cookie 或凭据。
