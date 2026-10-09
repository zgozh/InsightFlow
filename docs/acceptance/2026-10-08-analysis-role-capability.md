# 内部分析角色能力验收

## 本切片交付

新增 backend/app/analytics/agent/roles.py，提供与 principal、thread、run 绑定的 AnalysisRolesCapability。供应商支持边界限定为 ChatOpenAI：每个角色从现有 SDK root client 调用 with_options(max_retries=0)，并绑定新的 root 与 completions client；它保留原有 HTTP transport，不重建连接或关闭 Lead client。角色模型副本还隔离 Lead 的工具配置、callbacks、tags 和 metadata。未知 BaseChatModel 不会因具有 max_retries 字段就被接受。

SQLAnalyst、DataAnalyst、ReportWriter 各有独立模型副本、调用锁、最多两次已开始的输入尝试、成功结果缓存和角色级 token、响应字节、输入字节与超时上限。DataAnalyst 接受可选 keyword-only analysis_request，最多 8192 字符，并将其纳入模型输入和成功缓存指纹。Data 与 Writer 提示包含完整闭合响应 schema、枚举和字段约束。

SQLAnalyst 只返回受限 SQL 候选，不执行或授权 SQL。DataAnalyst 的来源快照会再次验证；其声明经 NumericClaim 和 verify_numeric_claims 整批校验，标签须与声明 ID 一一对应。ReportWriter 只选择固定章节和已验证声明 ID，结果经 VerifiedReportLayout 与 render_verified_report 复核；实际报告文字与数字仍由确定性 renderer 生成。

空指标 tuple 可以输入角色能力。DataAnalystResult 与 VerifiedReportLayout 没有指标版本字段；renderer 也明确说明展示标签不定义或证明指标语义。冻结 DTO 不保留“目录为空”状态，因此 Gateway/工具接线必须保留该状态，并在后续面向用户的报告中明确说明没有登记口径。

## 定点证据

从 backend/ 执行：

uv --no-config run --default-index https://pypi.org/simple --locked pytest tests/test_analytics_agent_roles.py -q
14 passed in 5.38s

    uv --no-config run --default-index https://pypi.org/simple --locked ruff check app/analytics/agent/roles.py tests/test_analytics_agent_roles.py
    All checks passed!

    uv --no-config run --default-index https://pypi.org/simple --locked ruff format --check app/analytics/agent/roles.py tests/test_analytics_agent_roles.py
    2 files already formatted

测试 double 是 ChatOpenAI 的本地子类。测试覆盖三个角色的独立调用与预算、缓存、身份和关闭边界、SDK root 零重试与回调隔离、HTTP 500 下只发一个 SDK 请求且 Lead retry 配置不变、analysis_request 输入与缓存分离、供应商失败与无效响应消耗尝试、工具调用拒绝、取消传播和超时 fail-closed、严格 JSON、数值和来源拒绝，以及验证到布局再到确定性渲染的成功链。最终上述定点命令均通过；未运行整仓测试或构建，也未调用真实供应商。

## 尚待接线

本切片没有连接 Gateway 或工具，也没有调用真实供应商模型。AS07、AS08、AS10 尚未完成；后续切片负责服务端创建与绑定能力、工具调用链和真实集成验收。
