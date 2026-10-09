# 指标显式授权：前端接线

用户已恢复任务，普通账号指标可用性是本切片目标。你是 `gpt-6-luna` / max 前端唯一实施者。读 frontend/AGENTS 与本提示词；后台契约已冻结，不再设计另一套 API。其他 Agent 可能独立改后端，禁止改 backend 和其 tests、Gateway、总 PROGRESS/INTERRUPTION 或 shared 架构决策。保留工作区既有品牌/黑洞修改。不派其他 Agent、不部署、不改真实账号权限/演示数据、不调用模型。

## 接口契约

路径由 core analytics API 既有前缀统一生成：

- GET `/admin/metrics/{metric_key}/grants` -> `{"principal_ids":["..."]}`。
- PUT `/admin/metrics/{metric_key}/grants/{principal_id}` **没有 body** -> `{"principal_id":"...","granted":true}`。
- DELETE 同路径 **没有 body** -> `{"removed":true}`。

当前 MetricView 不变；普通 `/metrics` 只读 active 且当前 principal 是 owner 或有确切 grant 的指标。草稿可预授权但启用后才可见；下线后不可见。授权仅开放指标定义，数据源查询仍要求独立 policy。同一用户能访问多个 owner 的同 key active 指标时，该歧义 key 隐藏，由管理员调整 key/重复授权；不要在UI随机选择定义。

## 实施

1. core/analytics/schemas.ts 增加严格grant列表/授予/撤销响应 schema，按现有 parseExternal 脱敏处理。授予响应必须是true且 principal_id 等于提交路径目标，撤销必须true；不得把 malformed/unknown字段当成功。使用既有 principal id 语义，1～64字符且无首尾空白/控制字符；仅URI路径编码，不把账号资料放 query key。
2. api.ts 增加三API函数。PUT/DELETE不得用jsonInit或提交任何body。保持同源fetcher、统一错误。hooks.ts 增加 grants key(包含metric key)、按打开状态enabled的读取、grant/revoke mutations。成功仅invalidate受影响metric grants和普通metrics目录，不全量invalidate。mutation固定使用提交时variables，切换指标不能把旧请求结果当新指标成功。
3. 现有 MetricAdminSection 的每行增加“授权”按钮，打开该指标独立授权面板/对话框。优先独立 `metric-grant-panel.tsx`，保持 admin-panels 修改很小，不重构已有2000行表单。面板含当前指标、已授权 principal IDs、目标用户ID输入、授予按钮、每个授权项的撤销按钮；空/加载/失败/重试/提交中/成功状态明确。输入label、键盘操作、关闭行为和触控尺寸沿用当前可访问组件。提交中禁重复操作，失败不会清空输入或显示成功。切换指标重置局部状态；普通账号不渲染面板，也不发管理grants请求。服务端403显示禁止访问，前端admin判断不是权限凭证。
4. 中英i18n同时加入所有新增文案，主要中文。说明草稿预授权、启用后可见、数据源权限独立；普通指标empty改为“联系管理员定义、启用并授予访问权限”。不新增用户搜索/账号profile API，不伪造授权数据。
5. 更新 frontend/AGENTS 对应用户可见行为与 `docs/current-capabilities.md` 指标可见性段（仅这一段；禁止改其他Agent/证据能力描述），补 `docs/acceptance/2026-10-08-metric-grants-frontend.md`。

## 文件所有权与 V2 验证

可改 frontend core/analytics api/schemas/types(必要时)/hooks、analytics-admin-panels、独立grant panel、analytics i18n三个文件及上述docs。直接相关现有 tests/unit/core/analytics/{schemas,api,hooks.dom}.test*、components/analytics/{admin-panels,pages}.dom.test* 与新grant panel tests。

补有价值行为测试：路径编码和无body、严格坏回执拒绝、mutation精确失效、普通账号不发管理请求、授予/撤销、错误重试/重复提交保护、关闭后换指标不显示旧目标授权。不要为每个label新增机械测试。先一次性完成连贯切片，再运行上述直接受影响的Rstest范围、tsc --noEmit及受影响ESLint/Prettier/diff。仅UI/API局部接线不自动构建整个镜像或全量E2E，真实部署验收留后续V3里程碑。

最终交付实际diff/文件清单、准确检查命令结果、已知限制。冻结文件给主会话独立审查，不自称已部署或完整15场景通过。
