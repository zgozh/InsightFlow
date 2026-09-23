# Phase 5B P0 Fix 01：清理 B3 遗留测试并守住外部沙箱边界

本提示词是 GPT 对 Luna 暂停点的审查裁决。只处理 P0；**不得开始 B4/B5，不得 amend B3**。现有四个未提交修改文件属于 Luna 的 P0 工作，必须保留并在其上做最小修正，不得重置。实施前先读根/涉及模块 `AGENTS.md`、`docs/prompts/phase-05b-luna-resume-after-b3.md`、`.reviews/phase-05b-handoff-to-luna.md`、Phase 5 manifest 与验证矩阵。

## 审查证据与裁决

- 当前基点 `0578a9e308834e340bffcda9ef39ecff3669dae7`；GPT 复核时有四个已修改文件，`backend/uv.lock` 未改。新建的**本提示词文件**是 GPT 授权的第五处变动；纳入 P0 修复提交即可，不要把它误判为 Luna 原有改动。
- GPT 在当前工作树运行 `uv run --locked python -m pytest tests/test_web_fetch_error_shell_meta.py tests/test_aio_sandbox_provider.py -q --tb=short`：`156 passed`。`_render()` 调用真实 Jina `web_fetch_tool` 和 Readability，仅把 `JinaClient.crawl` 换为 HTTP 桩；渲染结果再经真实 ToolProgress、ToolErrorHandling 与 `normalize_tool_result`。这是**分两段的内容链集成测试**，不是完整运行时工具装配测试，报告不得夸大。
- AIO 测试除去重外仍断言五个 mount path 的精确集合；服务端 `_validated_extra_mounts` 已删除，因此只能证明客户端 payload 形状。保留路径集合、去重与 `thread_data_mounts` 安全约束。保留可选外部 provisioner 客户端，不恢复仓库内服务。
- 完整离线套件的 `19 failed` 中，前四个新增失败经 GPT 定点复现；第五个 `test_extension_task_lifecycle::test_budget_exhaustion_mid_hook_logs_a_warning_not_a_traceback` 定点运行通过，原全量失败的 traceback 未提供，**原因未确定**，不得擅自认定为环境问题。
- 起始 tracked `2433` 与 manifest B4 `before.tracked=2422` 的差额 `+11` 已精确对账：Phase 5A 相对 `65b499d` 新增 7 个文档；B1 相对 forecast 多新增 3 个文档；GPT 的 `0578a9e` 续接提示词新增 1 个文档。B2/B3 实际净删除数分别等于 forecast。**不是漏删 11 个文件**；后续规模报告需保留该口径，不得为凑 2422 删除文件。本提示词及本次修复中的新增/删除再单列对账。

## 授权的窄范围修复

1. 保留并完善原 P0 四个文件。`backend/docs/CONFIGURATION.md` 新写的外部 provisioner 段落与新增测试 docstring/解释性注释，应按仓库“InsightFlow 自有内容中文优先”约定写中文；变量、API、协议名仍保持英文。配置示例不要把已不存在的 `http://provisioner:8002` 服务名当成可直接使用的外部地址；用清晰的外部地址占位，说明非可信内网应使用 HTTPS，API key 不可在明文公网链路发送。准确保留 `thread_data_mounts`：远程默认显式同步，只有双方确实共享同一按用户/线程隔离的数据目录时才可设 `true`。
2. `backend/tests/test_compose_default_bind_host.py`：开发 Compose 已没有 `provisioner` 服务。仅移除其旧 `env_file` 期望；仍逐一检查现存 Gateway/Frontend 的 `.env` 可选性与原有 loopback 端口约束。不要删整份测试。
3. `backend/tests/test_helm_extensions_config_writable.py`：三条用例均只验证已删除的 Helm chart；经确认没有 KEEP 用例后删除整份测试文件。把这项清单外删除显式记入 Phase 5 manifest 的执行偏差/最终报告，按仓库生成器与自检规则保持清单自洽；不要静默改 forecast 或删其它测试。
4. `backend/tests/test_soul_prompt_injection.py`：`_build_acp_section` 已删除，移除这一处过时 monkeypatch；保留并验证 `user_id` 传入 `get_agent_soul` 的原断言。若还遇到另一处已删 helper，先核对函数是否已不存在，再逐项处理，不得删整个用例。
5. **`test_docker_sandbox_mode_detection.py` 不是单纯旧断言。** 定点测试证明配置外部 `provisioner_url` 时 `scripts/docker.sh` 返回 `aio`；源码证明 `docker.sh` 与 `scripts/deploy.sh` 的 `aio` 分支会要求并向 Gateway 挂载宿主 Docker socket。保留外部 provisioner 客户端时，这既可能导致无 socket 的部署错误失败，也会在有 socket 时扩大宿主权限。请用最小修改让两脚本区分“本地 AIO/DooD”与“外部 provisioner”：前者维持已有 socket preflight 和 DooD overlay；后者**不要求、不挂载宿主 Docker socket，也不启动已删除的仓库内 provisioner 服务**。解析必须限定在实际 `sandbox:` 配置块，忽略注释/其它节；不要仅把测试期望从 `provisioner` 改为 `aio`。在现有测试文件中增加两脚本的定点断言：有外部 URL 且 socket 不存在时仍可走到 Compose 命令，Compose 参数不含 `docker-compose.dood.yaml` 或已删服务；无 URL 的本地 AIO 仍按原测试要求挂载 socket。若此修复需要超出这两个脚本及其直接测试，先停下报告。
6. 第五个间歇失败先做定点复现与错误日志收集，不先改生产逻辑或放宽断言。若下一次完整离线套件仍失败，保留完整 traceback、测试 ID 和运行上下文，定位根因后再修；若未复现，标记“单次全量失败、原因未定、后续全量未复现”，不要声称证明它是环境失败。

## 门禁、提交与回报

- 每一类修复先跑相应失败用例得到 RED，再修最小原因并验证 GREEN；尤其不能靠删 KEEP 测试或放宽安全断言转绿。
- 聚焦门禁至少覆盖上述四份保留的测试文件、外部/本地两种 Docker 检测与启动路径、原 P0 的 Jina/AIO 两份测试；执行 `ruff check`、`ruff format --check` 于改动的后端文件，并运行 manifest 自检和 `git diff --check`。
- 聚焦全绿后只跑**一次**完整离线后端套件（按交接备忘的 `-m "not live"`、`--ignore=tests/blocking_io`、`--locked`，捕获失败 traceback 到 `.reviews/`，不要仅用 `--tb=no`）。按具体 pytest node ID 对照 `.reviews/phase-05-b2-residual-failures.md`；P0 放行条件是没有新增失败，而不是要求已知 Windows/环境残差总数为零。若第五项再次失败，暂停并报告，不进入 B4。
- 本轮形成一个独立的 P0 修复提交，包含 Luna 原四个文件、授权的窄范围修复、清单/进度同步以及本提示词；不 `amend` `668dadd`，不动 `backend/uv.lock` 或固定 tag。提交后核对具体文件集合、工作树干净、parent 与测试证据。
- 回复用户一段可转给 GPT 的简短中文报告：commit/full SHA、文件清单、四个确定性失败及第五个间歇失败的结论、外部模式不挂 socket 的测试证据、完整离线套件准确计数与新增失败 ID、manifest 实测/forecast 对账、未验证事项。**提交 P0 后停在 GPT 复验，不启动 B4/B5。**
