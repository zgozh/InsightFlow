# PostgreSQL 分析运行探针准备记录

日期：2026-10-09。本切片准备了普通用户 datasource/metric 授权和单次真实模型分析探针；准备完成不代表 API、数据库或模型验收通过。

## 准备文件

- [分析运行探针](../../.reviews/final-postgres-runtime-20261008/runtime-probes/analysis_runtime_probe.cjs)：复用 Playwright API/browser fixture 模式，创建或核对合成 admin A、普通用户 B、PostgreSQL datasource、列策略、active revenue metric 与显式 metric grant。验证未授权前隐藏、B/匿名 admin 接口拒绝，以及已授权后的普通用户 API/browser 目录。
- [单次运行器](../../.reviews/final-postgres-runtime-20261008/runtime-probes/run_analysis_runtime_probe.ps1)：固定项目 `iflow-final-pg-20261008` 和 loopback `127.0.0.1:29388`；执行前要求调用方提供 Gateway/Frontend image ID，并核对四个服务、容器状态和端口绑定。image ID 原值保存在本地身份记录中，探针结果只保留其 SHA-256。
- DPAPI CurrentUser 凭据文件和运行结果文件仅会在之后获准执行时生成，位置分别为 `runtime-probes/credentials.dpapi` 与 `runtime-probes/runtime-probe-evidence.json`。账号随机生成；密码通过 stdin 传递，不进入命令行或标准输出。运行器需要显式 `-ExecuteOnce`，并在发送唯一的 `deepseek-flash` 请求前以独占创建方式写入 `positive-model-run.claim`；失败后不会自动重发。

## 后续调用

主会话审查后，可用已冻结的新镜像 ID 调用：

```powershell
.\.reviews\final-postgres-runtime-20261008\runtime-probes\run_analysis_runtime_probe.ps1 `
  -ExpectedGatewayImageId 'sha256:<gateway-image-id>' `
  -ExpectedFrontendImageId 'sha256:<frontend-image-id>' `
  -ExecuteOnce
```

运行时 datasource 使用 `env://ANALYTICS_CQ_PG_READONLY_CREDENTIAL`；schema/policy 只允许 `period`、`revenue`、`users`，拒绝 `description`、`customer_email`。脚本向 `monthly_metrics` 请求三个月 revenue 与合计，在内存核对 `1200.50`、`1800.00`、`900.75`、`3901.25`，不推断币种。它检查实际工具顺序、SSE 与 durable `analysis.stage` 事件（含 `workflow` 终态）、事件闭合字段、run/audit/report 投影、query artifact 地址与摘要、报告预览/download，以及 B 的浏览器报告、本人审计和刷新后的阶段历史。日志只记录 safe gate、状态、计数和摘要。

`verify-full` 由新 Gateway 的连接配置/该环境变量指向的 DSN 负责。本探针不读取容器环境变量或凭据，也不单凭成功查询声称验证了 TLS 模式；该模式须由启动切片的安全配置检查确认。

AS04/05 的后续扩展入口位于 `main()` 中普通用户目录检查完成后、`createAndRunAnalysis()` 之前，可复用同一 fixture 增加不触发模型的授权场景。AS11/12 的续跑或恢复检查应接在 `createAndRunAnalysis()` 内既有 `threadId`/`runId` 验收点，或由独立的 no-model runner 接收这些 ID；不要再次调用本次单次运行器。此准备没有实现失败矩阵、调度或恢复逻辑。

## 检查与未执行项

实际 API 请求模型字段与 [analytics API models](../../backend/app/analytics/api/models.py)、[analytics API routes](../../backend/app/analytics/api/router.py) 对照：datasource create、schema/policy PUT、metric create/grant、普通用户 datasource/metric、审计与报告索引字段均按源码闭合校验。durable 阶段信封按 Gateway 直接契约要求 `event_type=analysis.stage`、`category=analysis`、空 `content`，分页使用记录 `seq`。query artifact 的 create-only 实现已静态对照 [analysis query artifact store](../../backend/app/gateway/analysis_query_artifacts.py)；运行探针只读固定路径两次并核对内容地址、digest 和 preview/download 一致性，不尝试写入验证。

已通过：`node --check`、PowerShell Parser AST，以及三份自有文件的尾随空白扫描和回读。未调用 API、创建账号或数据、启动/检查容器、访问业务 PostgreSQL、发送模型请求或操作 29384/29385；以上真实验收仍待主会话审查后执行。

## 身份 helper 跟进

Windows PowerShell 5 的默认代码页为 936；runner 原先没有 UTF-8 BOM，中文注释在宿主默认解码下吞掉紧随其后的初始化语句。现已仅为 runner 加 UTF-8 BOM；去掉 BOM 后的正文 SHA-256 前后均为 `f3720d395574bca8ce08cbe69811c0d5d9e9614ae63072eac4976117442d4a7f`，正文未变。PowerShell Parser AST 无语法错误。无 `-ExecuteOnce` 正式预检得到 `accepted=true`：4 个容器/服务均被读取且 running，精确服务集和 Gateway/Frontend 镜像 ID 匹配，唯一发布端口为 Nginx 的 `127.0.0.1:29388`，无其他发布端口或 29384/29385；随后按设计以 `explicit_execute_once_required` 停止。此次未读取凭据、写入身份/探针证据、调用 API、创建 seed、发起模型请求或改变容器生命周期；业务探针仍待主会话审查。

## 正例 oracle 复核修正

月度 oracle 现严格核对 `period -> revenue`：2026-01 为 1200.50、2026-02 为 1800.00、2026-03 为 900.75；要求三行和唯一 period，不再对十进制字符串排序。artifact 列检查只拒绝 `description` / `customer_email` 名称并要求字符串列名，允许 `total_revenue` 等派生 alias；这项拒绝检查不代表授权证明，月度 oracle 仍要求原始 `period` 与 `revenue` 列。模型请求提示现明确要求生成并发布经营分析报告，逐月列出 revenue 和合计，数值保留两位小数且不推断币种或物理单位。

已通过：`node --check`；离线 VM fixture 直接提取并调用 CJS 中的纯函数，正确月份映射通过、月份错配与重复 period 拒绝、`total_revenue` alias 通过、`description` 和 `customer_email` 拒绝。没有运行 CJS main，也未调用 API、创建 seed 或发送模型请求。
