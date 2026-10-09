# 数据声明契约与分析入口定点检查

本切片仅做离线函数复现和前端源码审查；没有调用模型、访问 live 服务或操作容器。

## 数据声明契约

使用 `backend/tests/test_analytics_agent_roles.py::_snapshot` 的合成证据元数据，构造三条月收入结果行，并调用实际 `_parse_data_result`。三个 `cell` 声明各引用对应月份单元格，`sum` 声明引用全部三行；未知单位置空，标签不含数字字符。

执行命令：

```powershell
& 'backend/.venv/Scripts/python.exe' '.reviews/final-postgres-runtime-20261008/runtime-probes/offline_data_contract_probe.py'
```

结果：`{"accepted": true, "labels_have_no_numeric_characters": true, "monthly_period_references": true, "sum_total": "3901.25", "unknown_unit_null": true, "verified_claims": 4}`。首次探针把 JSON 字符串直接传给解析器，入口要求 `AIMessage`；改用现有消息类型后，上述命令通过。这是探针输入包装修正，不是产品失败。

对照 `roles.py::_DATA_PROMPT`、`roles.py::_parse_data_result` 与 `domain/claims.py::NumericClaimOperation/verify_numeric_claims`，没有发现契约不一致：operation 名称一致；声明值要求普通十进制字符串并按 `ROUND_HALF_UP` 复核；金额列支持十进制文本；period/unit 接受精确证据单元格引用或 `null`；行号和列名按同一快照精确解析。这个离线结果不能解释先前 live `numeric_validation_failed` 的具体子分支，现有持久消息没有保留候选 payload。

## 前端实际入口

工作台布局要求登录。侧边栏“新建分析”指向 `/workspace/analysis/new`；当前路由由 `analysis/[thread_id]/page.tsx` 接收，`thread_id === "new"` 时渲染通用 `ChatPage(mode="analysis")`。用户首次提交时，页面创建 `analysis` 类型 thread，校验返回的 `analysis_mode` 后再发送问题；已有 thread 只有 `analysis_mode === true` 才进入分析视图。这里没有单独的新建页表单。

侧边栏“分析会话”当前指向 `/workspace/chats` 的通用会话列表；其余入口是“数据源”“指标”“报告”“定时任务”“审计历史”。数据源和指标目录对登录用户读取可见，管理面板仅在前端识别为管理员时显示；报告页列出已发布报告并打开对应分析 thread；审计历史显示当前主体记录，管理员另有显式主体查询；定时任务页提供任务配置和运行历史，源码未按管理员角色隐藏该页面。

分析 composer 传入的 `settings.context` 是模型、运行模式和推理强度等通用线程设置，并支持普通消息/附件；`chat-page.tsx` 没有调用 datasource/metric catalog hooks，也没有数据源或指标选择控件。因而目录授权不会由用户通过 UI 选择并注入分析上下文。现有后端 `inspect_business_catalog` 工具按当前主体返回可访问数据源和 active 指标；工具说明要求 SQL 前调用它，`query_business_data` 再要求使用目录返回的 datasource id，并在服务端按主体校验访问。当前选择路径由 agent 依赖该目录，不是显式 UI 选择。

## 交回审查的建议

若需定位 live 数值失败，最小诊断是在既有 `_parse_data_result` 的具体拒绝分支记录固定内部 reason enum，不记录模型候选、请求体、SQL、行值，也不改公开错误码、事件 schema、权限或验证规则；本切片未实现。UI 后续可先评估用现有新分析入口预填自然语言请求，把 `inspect_business_catalog` 保留为资源与授权真值来源；是否增加可选数据源/指标选择，应由 Principal 结合现有工具路径审查后决定，不在本切片添加 context 契约。
