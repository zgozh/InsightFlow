# PostgreSQL 正例实时运行验收（2026-10-09）

**结果：未通过。** 29388 上唯一获准的 ExecuteOnce 已执行并创建 claim，但 run 以 error 结束；没有重发模型调用，也没有删除 claim。

## 运行边界与夹具

- 目标为 127.0.0.1:29388，使用既有 iflow-final-pg-20261008 四服务和既有 PostgreSQL fixture。运行前已有容器均为 running，Gateway health 为 200；未重建容器、未新建容器、未访问旧端口 29384。
- 正式 runner 的镜像身份 guard 通过：Gateway sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63、Frontend sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c；两项均为完整 64 位 image ID，tag 匹配。
- 合成管理员 A、用户 B、datasource、schema、policy、metric 均已存在。脚本核对了 B 的现存 policy 与 fixture 的完整预期字段相等，且现存 metric grant 与 B 可见定义一致；按夹具恢复规则记录为既有授权，不把本轮描述成授权前隐藏验证，也没有清除权限。
- 先前诊断中 grant PUT 返回 200，普通用户管理接口返回 403，匿名管理接口返回 401。最初的 HTTP 422 未复现，没有据此推断或修改生产契约。

## 命令与结果

正式运行前，以下定点检查通过：

    node --check .reviews/final-postgres-runtime-20261008/runtime-probes/analysis_runtime_probe.cjs
    node .reviews/final-postgres-runtime-20261008/runtime-probes/analysis_runtime_probe.cjs --offline-authorization-resume-check

离线分支结果为 outcome=passed，ungranted=true、exact_existing_authorization=true、conflict_rejected=true。run_analysis_runtime_probe.ps1 的 UTF-8 BOM 保持存在。

正式单次调用使用从既有 Gateway、Frontend 容器直接读取并比对 tag 的完整 image ID：

    .\.reviews\final-postgres-runtime-20261008\runtime-probes\run_analysis_runtime_probe.ps1 -ExpectedGatewayImageId $gatewayImageId -ExpectedFrontendImageId $frontendImageId -ExecuteOnce

服务与身份检查通过，API 建线程、SSE run 和读取 run 均返回 HTTP 200。正例最终返回 outcome=failed、failure_stage=verify_terminal_run_and_model、failure_code=run_not_successful。claim 文件 positive-model-run.claim 已存在；此后没有再次执行正式 runner。

随后使用合成用户 B 的会话和私有 context 中已按 SHA-256 精确匹配的线程/run ID，仅调用只读 run 与 durable events API。终态摘要保存在 .reviews/final-postgres-runtime-20261008/runtime-probes/runtime-probe-terminal-summary.json；原始不透明 ID 仅保存在同目录的 ignored 文件 positive-analysis-private-context.json。摘要不包含凭据、请求/响应正文、SQL、模型/provider 文本或结果行。

终态为 run.status=error，无稳定 stop_reason。共读取到 34 条 durable analysis.stage 事件。最终事件为 workflow/failed/unavailable；事件序列中出现 authorization/blocked/policy_denied，之后有 sql/blocked/attempt_limit 和 data/failed/numeric_validation_failed。一次 execution stage 为 succeeded/ok，记录行数为 3；没有保留或输出结果行。报告、下载和浏览器验收因终态失败未执行，因此本记录不宣称报告产物验收通过。

## 安全与范围证据

- 本切片只修改 .reviews/final-postgres-runtime-20261008/runtime-probes/ 中的 fixture/探针，以及本验收记录；没有修改生产代码或 API 契约。
- 模型调用额度只消耗一次。claim 保留，禁止删除后重发。
- 正例失败的准确终态及稳定 stage code 已记录；该结果不等于 PostgreSQL 正例验收通过，也不代表整体发布验收完成。
