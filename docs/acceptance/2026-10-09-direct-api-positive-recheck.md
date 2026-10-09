# 2026-10-09 直接 API 正例重测

## 执行结果

单文件 COPY 镜像构建成功并只更新既有 29388 Gateway。基底为原 Gateway 镜像 `sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63`，构建上下文只有 `Dockerfile` 与 `roles.py`；`roles.py` SHA-256 为 `CFB7073EFFC5BF584337D24673A90B841E83BD8120190988BBA9AAF8F96AB890`。Docker 不接受在 `FROM` 中直接解析本地 image ID，首次构建被 registry 403 拒绝；随后给同一基底 image ID 加本地临时 tag 并从该 tag 构建，产物为 `sha256:c5a7a0c535ff06fe680b4f0a04304beed3c839f940bbdfa0825e0e213e96d3da`。

Gateway 通过既有 `runtime.compose.yaml` 以 `--no-deps --no-build --pull never gateway` 更新，复用当前容器内认证配置与既有挂载；Gateway 状态为 `running|healthy`。Frontend 仍为 `sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c`。Frontend、Nginx、Redis 均未重建。首次 compose 因未注入 `DEER_FLOW_SKILLS_PATH` 在变量解析期退出，未改变容器；重试时从既有 Gateway/Nginx 容器挂载和 Gateway/Frontend 环境中以内存复用原值，没有输出凭据。

实际运行命令：

```powershell
& '.reviews/final-postgres-runtime-20261008/runtime-probes/run_analysis_runtime_diagnostic.ps1' `
  -ExpectedGatewayImageId 'sha256:c5a7a0c535ff06fe680b4f0a04304beed3c839f940bbdfa0825e0e213e96d3da' `
  -ExpectedFrontendImageId 'sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c' `
  -ExecuteOnce
```

探针身份门禁通过（目标服务集合 4/4、运行 4/4、镜像匹配、29388 loopback、旧端口不存在）。仅发起一次新分析 run：thread 创建与 run stream 均为 HTTP 200，收到 SSE terminal 和 28 个阶段事件；随后 `GET run` 为 HTTP 200，但最终契约断言失败，稳定探针码为 `run_not_successful`，探针失败阶段为 `verify_terminal_run_and_model`。Gateway 本次时间窗只提取固定安全枚举，观测到 `analysis_data_parser_rejected.label_domain` 两次。探针未输出底层分析阶段的额外 status/code，因此不据此推断。

新 claim `runtime-probes/positive-model-run-diagnostic.claim` 已创建；旧 `positive-model-run.claim` 保留。thread/run opaque IDs 已写入私有文件 `runtime-probes/positive-analysis-diagnostic-private-context.json`，本记录不包含其值。未发第二次模型请求，也未读取其它日志正文、消息或审计内容。
