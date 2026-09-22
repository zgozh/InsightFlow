# Phase 4：InsightFlow 产品工作台

## 1. 目标与边界

本阶段把 Phase 2 的受控数据链和 Phase 3 的 Agent workflow 交付为可演示、可管理、可追溯的
InsightFlow 产品界面。交付必须覆盖：

- InsightFlow 品牌、中文优先且中英可切换的 Landing 与 Workspace 导航；
- 管理员的数据源、Schema、访问策略和指标管理；
- 普通用户可见的数据源/指标目录、查询审计和报告索引；
- 从现有 LangGraph 消息流投影出的经营分析轨迹与 evidence 卡片；
- 报告 artifact 的持久化索引和安全下载入口。

本阶段不物理删除 DeerFlow 的旧路由、provider、channel、skill 或依赖；这些属于 Phase 5 的
引用扫描和删除清单。本阶段也不新增图表库、状态管理框架、数据库、容器、Redis、队列或后台线程，
不在前端重做 SQL policy、权限判定、evidence 摘要或审计逻辑。

## 2. Phase 3 复验裁决

Phase 3 提交 `7bd21d7721e3caf3cc7cc1b90bb9d3b51b7b2d8a` 通过复验。

`query_business_data` 的模型可见 schema 精确为 `{datasource_id, sql}`；额外字段在工具 schema
层被排除，真正的 principal 始终由认证 runtime 注入。V1 接受该行为，不为“额外字段行为级报错”
修改 DeerFlow 通用工具装配层。必须保留以下回归断言：伪造 `principal_id` 不进入 schema、不能改变
实际 principal，输出不含伪造值或认证信息。若未来对第三方直接工具调用开放公共入口，再单独设计通用
严格参数 seam，不在当前阶段预埋。

## 3. 产品信息架构

```text
/                              InsightFlow 产品 Landing
/workspace/analysis/new        新建经营分析（复用现有 chat 创建链）
/workspace/analysis/[thread]   分析会话 + artifact + 结构化轨迹
/workspace/datasources         可访问目录；管理员可管理 datasource/schema/policy
/workspace/metrics             指标目录；管理员可维护指标版本
/workspace/reports             principal-scoped 报告索引与 artifact 入口
/workspace/history             principal-scoped SQL 审计历史
/workspace/scheduled-tasks     复用现有定时任务页面
/workspace/settings            复用现有设置入口
```

`/workspace/chats/**` 在 Phase 4 保持兼容，`analysis/**` 复用同一 thread/chat 主链，不复制 streaming
状态机。旧路由是否删除由 Phase 5 决定。

Workspace 使用现有 Sidebar、Resizable layout、message、artifact、todo、subtask 和 SSE 能力。
桌面端分析页采用“对话主区 + 可折叠轨迹区”；窄屏下轨迹变为 drawer/折叠区，禁止水平溢出。

## 4. 视觉与交互规范

- 风格：克制、专业、数据产品导向的 Minimal/Swiss dashboard；不使用 AI 紫粉渐变、夸张动效或
  营销式 3D 装饰。
- 复用现有 CSS token、Tailwind 和 shadcn primitive；不引入新字体网络依赖或新 UI 库。
- 图标统一使用现有 Lucide，不用 emoji 充当功能图标。
- 正文对比度至少 4.5:1；键盘焦点可见；点击目标至少 44×44 px；颜色不能是唯一状态信号。
- loading、empty、error、forbidden、disabled、stale-version 和 retry 状态必须显式；异步提交期间
  禁用重复操作。
- 验证 375、768、1024、1440 px；尊重 `prefers-reduced-motion`，hover 不造成布局位移。
- 所有 InsightFlow 新文案进入现有 i18n，至少提供 `zh-CN` 与 `en-US`；中文是设计基准。

## 5. 前端数据边界

新增 `frontend/src/core/analytics/`，内部按 `types.ts`、`schemas.ts`、`api.ts`、`hooks.ts`、
`trace.ts` 划分：

- 所有 HTTP 都使用现有认证 fetcher，写请求自动继承 CSRF；不得直接调用 `globalThis.fetch`。
- 外部 JSON 必须经 Zod 严格解析；解析失败显示稳定的通用错误，不把未知 payload 原样渲染。
- TanStack Query key 以 `analytics` 为根；mutation 成功后只失效受影响的精确 key。
- 管理按钮按 `user.system_role === "admin"` 隐藏或禁用，但服务器 403 仍是最终授权边界。
- 普通 datasource 视图不得出现 `owner_id`/`secret_ref`；管理员只显示 opaque `secret_ref`，不解析
  或探测凭据。
- SQL、plan token、凭据、DSN、原始异常和结果行不得写入浏览器日志、URL、localStorage 或 query key。

## 6. 报告索引补口

Phase 3 已生成 artifact，但尚无 `analysis_reports` 索引。Phase 4 以 Analytics bounded context 自有
前向迁移增加 `analytics_analysis_reports`，至少保存：

- `id`, `principal_id`, `thread_id`, `run_id`, `artifact_path`；
- `title`, `status`, `evidence_ids`, `created_at`；
- 唯一发布键，保证同一 run/artifact 重试幂等。

禁止保存原始 SQL、结果行、prompt、chain-of-thought、凭据、DSN 或 artifact 内容。`evidence_ids`
只接受有限数量的 64 位小写 SHA-256；`artifact_path` 必须是规范化的
`/mnt/user-data/outputs/` 下相对目标，拒绝 `..`、反斜杠、空段、NUL、目录本身和越界路径。

新增 Lead-only `publish_analysis_report` 工具：模型参数只包含 `title`、`artifact_path`、
`evidence_ids`；principal/thread/run 从受信 runtime 派生。它只登记索引，不读 artifact 内容，不接受
principal/thread/run/status/created_at。general-purpose 与 bash subagent 的实际工具 schema 中都不得
出现该工具。Skill 顺序固定为：生成 artifact → `present_files` 成功 → 发布报告；发布失败必须如实
报告，不能把未登记报告描述为已保存。

HTTP 只提供 principal-scoped 的只读分页列表；管理员若需要查询其他 principal，必须走显式 admin
端点。报告打开链接必须仍经过现有 thread/artifact ownership 检查，不签发公共 URL。

## 7. Analytics 管理页

### 7.1 数据源

- 普通用户只读展示自己可访问的数据源。
- 管理员可创建、编辑、启用/停用自己的 datasource；engine 创建后不可在编辑表单中改变。
- Schema 编辑以结构化 relation/column 行为主，可提供受控 JSON 导入，但提交前必须本地严格校验；
  `expected_version` 来自最后一次成功读取，不允许用户随意覆盖。
- Policy 必须明确 principal ID、relation/column access 与 allowed functions；危险操作二次确认。
- `version_drift`/`stale_expected_version` 显示“刷新后重试”，绝不自动覆盖新版本。

### 7.2 指标

- 目录展示 key、名称、说明、dimensions、version、status。
- 管理员创建/更新时版本必须显式前进；退役使用现有 DELETE 的 status 语义，不宣称物理删除。
- expression 是定义文本，不在浏览器求值，不把它包装成可执行 SQL。

### 7.3 历史

- 使用后端 keyset cursor；页面只持有 `before_started_at` + `before_id`，不能改成 offset 猜测。
- 用户只读自己的记录；管理员查询他人必须显式填写 principal，默认不跨用户。
- 展示安全字段：phase/status/code/risk/rows/bytes/cost/latency/time 与 hash/digest 缩略值。
- 不展示或推导 raw SQL、结果行、凭据和内部异常。

## 8. 分析轨迹与 evidence

轨迹是现有 LangGraph message/tool event 的纯投影，不建立第二套运行状态源：

- `write_todos`/todo state → 分析计划；
- `inspect_business_catalog` → 目录发现阶段；
- `query_business_data` → 受控查询阶段；
- `task`/subtask receipt → Data Analyst / Reviewer 生命周期；
- `present_files` → artifact 阶段；
- `publish_analysis_report` → 报告登记阶段。

解析器只识别上述稳定工具名与已批准的 JSON 字段，未知/畸形 payload 显示“无法解析的安全事件”而
不是直接渲染对象。`query_business_data` 卡片允许展示 code、risk、row/byte count、estimated rows、
engine cost、truncated、schema/policy version、evidence ID 和安全 digest；禁止展示 tool args 中的 SQL、
结果 rows、plan token 或异常原文。evidence ID 提供复制；结果表仍由消息/Artifact 既有安全预览负责。

刷新后从 checkpoint 消息重建相同轨迹；流式增量与历史重放必须去重并保持稳定顺序。轨迹只展示
结构化状态，不展示、推断或命名为 chain-of-thought。

## 9. 品牌与开源归属

- 页面 title、description、workspace header、welcome、Landing 和 about 的产品名称改为 InsightFlow。
- 移除产品 UI 中 deerflow.tech、ByteDance GitHub、issue、support 邮件和 GitHub stars CTA。
- 不删除 MIT LICENSE、上游版权或 README 中的派生说明；About 必须保留“基于 DeerFlow
  v2.1.0-rc0 深度重构”的清晰归属。
- Phase 4 只替换用户可见品牌和默认入口；全仓品牌残留清单与物理删除在 Phase 5 完成。

## 10. 验收

1. Phase 3 focused 回归保持绿色，伪造 principal 测试仍在。
2. 报告发布默认拒绝缺少可信 principal/thread/run、越界路径、坏 evidence、subagent 调用；幂等重试
   不产生重复行。
3. 报告 API、datasource、metric、audit 全部 principal 隔离；普通用户看不到管理表单。
4. 前端 schemas/API/hooks/trace 使用 unit test；表单、错误、键盘和响应式关键路径用 DOM test。
5. Playwright 覆盖登录后：新建分析、查看 evidence 轨迹、管理员管理 datasource/metric、查看报告；
   网络 fixture 不含 token、凭据或真实 PII。
6. `pnpm check`、focused unit、focused E2E、`pnpm build`、后端 focused pytest/ruff 和
   `git diff --check` 全绿。
7. 不新增依赖，lockfiles、Docker、固定 tag/tree 不漂移；工作树干净。
