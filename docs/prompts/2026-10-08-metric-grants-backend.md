# 指标显式授权：后端实施切片

## 背景与职责

用户正在用普通账号验证数据源、指标、报告和审计，询问是否只有管理员能完整使用。产品边界是管理员配置治理资源、普通用户使用显式授权的资源并发布自己的报告。已确认 `SqlMetricRepository` 只读创建者自己的指标，当前没有管理员向普通用户授权指标的路径。

主会话负责方案与独立审查；本任务由 `gpt-6-luna`、max 实施。先读根、backend、app/analytics 的 AGENTS.md 与本提示词。禁止覆盖已有耐久证据、预算、品牌等未提交成果。不再派子 Agent。只做本切片，不做前端、Gateway evidence bridge、模型角色或部署。

## 冻结契约

1. 指标写入、所有状态的管理读仍是 exact-owner。给 MetricRepository 加 `get_owned(owner_id, metric_key)` / `list_owned(owner_id)`，AnalyticsAdministration 使用它们，不能因获授权指标混入管理目录而编辑他人指标。所有接口 keyword-only。
2. 普通 MetricCatalog 只返回 ACTIVE 且创建者为当前 principal 或存在精确指标 grant 的指标。没有 grant 默认拒绝；DRAFT / RETIRED 始终不进入普通目录。管理员自己的 ACTIVE 指标可用于指标目录，但数据源查询权限仍独立要求 policy。
3. 保留现有 MetricView、metric_key 和 Agent catalog 契约。跨 owner 同 key 可在管理库存在；如果一个 principal 同时可访问多个 ACTIVE 同 key 指标，普通 list 必须剔除该歧义 key，get 返回 None，不按顺序选择，不把不同口径混同。此 V1 限制在对应文档明确写出，管理员通过撤销重复授权或另起 key 解决。不引入 opaque ref / 全局唯一 key 或旧数据重命名。
4. 写侧 MetricRepository 增加显式 `list_grants(owner_id, metric_key)->tuple[str,...]`、`grant(owner_id, metric_key, principal_id)->None`、`revoke_grant(...)`；稳定排序。只存 principal_id，不暴露用户 profile。Administration 每次先 exact-owner 确认指标，不存在和非 owner 都统一404，存储失败继续稳定脱敏。grant/revoke 幂等；撤权下一次目录读取即消失。DRAFT 可预先授权，但只有 ACTIVE 可读。
5. 新表 `analytics_metric_grants`：复合主键 metric_owner_id / metric_key / principal_id，created_at UTC，复合外键只指 Analytics 内 `analytics_metrics(owner_id,key)`，读授权有 principal_id 索引。禁止 Harness 身份 FK。目标 principal 使用与现有 policy 一致的身份语义，并拒绝空白、超长、控制字符；不将 * 解释为通配符。不新增账号发现/搜索 API。
6. 新 additive Analytics Alembic revision `0004_metric_grants`，down_revision 对齐实际新0003。不改历史迁移，不改旧指标行，不为旧指标自动授予任何他人权限；降级只移除 grant 表。更新 migrate-head 断言，验证0003已有指标/证据升级保留和降级可读。
7. HTTP 延续现有 `/api/analytics/admin` 管理命名与统一错误风格，使用既有 require-admin 依赖：
   - GET `/metrics/{metric_key}/grants` -> `{"principal_ids": ["..."]}`。
   - PUT `/metrics/{metric_key}/grants/{principal_id}`，无请求体 -> `{"principal_id":"...","granted":true}`。
   - DELETE 同路径 -> `{"removed":true}`（沿用 policy 删除回执）。
   当前 owner 来自认证上下文。禁止在 body/query 接受可修改的 metric owner。管理员 B 不得管理 A 的指标/grant；普通用户任何 grant 管理返回403；匿名401。固定 route/resource 不泄露非 owner 指标。
8. 普通 GET /metrics 响应结构不变；严格前端 schema 当前无须变动。指标授权仅是口径可见性，不附带 datasource/schema/policy/SQL 权限，更不能扩展 analysis 最终三工具白名单。

## 文件所有权

仅改后端 Analytics 的 metric persistence/domain(确有必要时)/management/API/exports/模型与0004迁移，直接相关的 backend tests，`backend/app/analytics/AGENTS.md` 指标段，`docs/acceptance/2026-10-08-metric-grants-backend.md`。可以调整测试 fake MetricRepository 以满足新增 owned/write 端口。不得改 frontend、总体 PROGRESS/验收矩阵、Harness、config/secrets、真实持久演示数据。若对保存逻辑发现无关并发问题，不扩大修复范围。

## 验证 V2

确认授权缺陷的回归先行（B 看不到 A 的 active metric；grant 后可读，C 不可读；revoke 后隐藏）。覆盖 owner-only 管理、防越权写、draft/retired 状态、同 key 歧义、幂等授予撤销、grant 不授予 datasource、服务重建后 grant 保留。API覆盖 anonymous401 / normal403 / foreign-admin404 和严格请求体。迁移空库head与旧0003非空库升级/降级、相邻模块边界测试。

先运行最小直接相关测试，最终按实际影响选择 analytics repositories、management、api、migrations、boundaries 中受影响的测试文件/用例，及受影响文件 Ruff check / Ruff format --check / git diff --check。不机械跑全 backend 或生产镜像构建；若真实跨模块失败，说明证据再扩大。不访问真实业务数据库或调用付费模型。

## 交付

报告实际改动文件、关键 diff/接口语义、每条实际执行检查与通过/失败数、限制。报告明确这是源码/定点验收，未部署29384，管理员仍须显式授权普通账号。不得自报 AS-01～15 完整发布验收完成。完成后冻结文件交主会话审查。
