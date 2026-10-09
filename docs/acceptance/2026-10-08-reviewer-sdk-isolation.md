# Reviewer SDK 重试与回调隔离修补

## 变更

- Reviewer 仅接受 `ChatOpenAI` 及其子类，并在可信绑定时制作专用副本；绑定来源仍保留为原 Lead 模型，用于同一 run 的幂等绑定判断。
- 副本使用 `root_async_client.with_options(max_retries=0)` 创建的新 SDK root 和 completions client。同步 SDK client/root 从副本移除；缺少可隔离的异步 SDK client 形状时绑定失败关闭。
- Lead 模型保持原样。Reviewer 副本清除 callbacks、callback manager、tags、metadata 和工具默认参数，并保留现有 DeepSeek token 上限、thinking 关闭及审核响应约束。
- 离线测试 double 改为 `ChatOpenAI` 子类；新增 SDK 返回 HTTP 500 时只发出一次请求的 MockTransport 回归，以及模型自带/ambient callbacks、元数据和工具默认值隔离断言。

## 验证

本机 `uv` 要求 `--default-index` 放在 `run` 子命令后。所有命令使用 `--no-sync`，没有访问真实模型或网络。

- 首次 Reviewer 文件测试命令：`uv --no-config run --default-index https://pypi.org/simple --locked --no-sync python -m pytest tests/test_analytics_agent_reviewer.py -q`。结果为 **27 passed, 2 failed**；两项失败均来自测试夹具：LangChain 向原模型 metadata 注入 `lc_versions`，以及取消测试仍修改原模型的标量延时。新 SDK HTTP 500 重试回归已在该次运行中通过。
- 修正夹具后重跑两个受影响节点：`uv --no-config run --default-index https://pypi.org/simple --locked --no-sync python -m pytest tests/test_analytics_agent_reviewer.py::test_reviewer_uses_the_bound_lead_model_without_tools_or_inherited_run_callbacks tests/test_analytics_agent_reviewer.py::test_reviewer_timeout_fails_closed_and_cancellation_propagates -q`：**2 passed**。
- `uv --no-config run --default-index https://pypi.org/simple --locked --no-sync ruff check app/analytics/agent/reviewer.py tests/test_analytics_agent_reviewer.py`：通过。
- `uv --no-config run --default-index https://pypi.org/simple --locked --no-sync ruff format --check app/analytics/agent/reviewer.py tests/test_analytics_agent_reviewer.py`：通过，2 个文件均已格式化。
- `git diff --exit-code -- backend/uv.lock`：通过，锁文件未改变。

两项修正后的测试节点和首次运行中其余通过项分批记录；修正后没有重新运行整个 Reviewer 文件。

V0 注释收尾：本次新增的 Reviewer 英文解释注释已中文化；未改执行代码或测试，也未运行测试。
