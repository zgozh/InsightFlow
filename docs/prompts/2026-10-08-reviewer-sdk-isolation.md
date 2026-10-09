# Reviewer SDK 重试与回调隔离定点修补

实施 gpt-6-luna/max。所有权仅 backend/app/analytics/agent/reviewer.py、backend/tests/test_analytics_agent_reviewer.py、docs/acceptance/2026-10-08-reviewer-sdk-isolation.md。并行角色worker只修改roles.py/对应测试/其独立报告；双方不得修改对方文件，不抽取或改共享helper。

主会话从本机langchain_openai/chat_models/base.py:1183/1253/1828确认：max_retries在模型初始化时写入SDKroot，而调用走已创建async_client。Reviewer当前保存Lead实例，仅空config callbacks与deepseek token field复制，底层SDK可能继续默认重试，模型自身callbacks也未清空。本修补只补现有“独立零工具、无provider retry”承诺，不添加角色、事件或新公开API。

在可信base model绑定时制作Reviewer专用副本，保留 __bound_source 为原Lead用于幂等绑定；清空model callbacks/tags/metadata与工具默认配置，不能修改Lead原实例。生产支持边界可限定ChatOpenAI及其兼容子类，其他无法证明SDK无重试的模型fail closed；不在生产代码按测试类/模块名放行。已有测试double可改为ChatOpenAI本地生成子类，使用纯测试key且不开网络。

ChatOpenAI副本不仅max_retries=0，同时通过既有root_async_client.with_options(max_retries=0)新root+新root.chat.completions更新副本；Responses路径使用新root。同步root/client若保留也同样隔离。缺合法client形状时拒绝，不重建读取环境密钥、不关闭原Lead SDKclient、不打印client。保持当前deepseek-flash正确token上限和关闭thinking处理、scope/预算/缓存/取消与闭合审核响应语义。

V2验证：既有Reviewer定点文件 + Ruff/format；增加httpx MockTransport返回500的真实SDK行为回归，证明一次Reviewer调用仅一次HTTP请求且原Lead SDK retry配置不变；自带回调不接收Reviewer原始输入。保留既有Reviewer拒绝/timeout/cancellation保障。不调用真实模型、不构建、不跑全套，uv --no-config --default-index https://pypi.org/simple --locked，锁文件不变。

完成后冻结，报告准确命令与实际结果。新角色worker不依赖Reviewer本次改动，后续Gateway/报告集成会在双方冻结后开始。
