# 2026-10-07 续接：剩余对接与简历能力核对

执行者 `gpt-6.1-sol` / medium。用户要求尽快完成二开，并列清 Agent 功能、架构与改造内容。主会话已独立阅读前端 diff、BlackHole 动效代码、资源生成脚本与署名，并目视桌面/手机最终完整截图：6F3F21 本地视觉接受；部署证据仍缺，不可宣称整体发布完成。

本切片独占：当前 UI 交付文档的状态收口、生成脚本必要格式修正、`docs/current-capabilities.md`、6F3F20 acceptance、PROGRESS、README/README_zh 中实际现状的必要同步。其他生产后端代码先不动，发现真实任务缺陷报告主会话后再分派。前端工作已冻结，不重复其通过的检查。

## 先收口本地 UI

- `frontend/scripts/generate-black-hole-assets.py` 是新增 Python 代码，先用现有 backend Ruff 做该文件 check/format；只做必要格式修正，确认生成资产不因格式改变而变化。不跑后端应用测试。
- 6F3F21 acceptance/PROGRESS 写清主会话独立目视已通过，未部署状态仍保留。去掉已经过时的“不得启动 6F3F20”句子，不把待验收整体状态改成 Complete。
- README 的用户可见首页变化与能力说明需要同步；英文 README 保持语言，中文 README 以中文更新，尽量引用能力文档，避免重复维护长表。

## 有界恢复与已有对接切片

先读 `docs/prompts/phase-06f3f20-surprise-user-flow-and-release-triage.md`。Docker engine pipe 目前缺失。核对 Docker Desktop 是否已安装；若存在允许用 `Start-Process -WindowStyle Hidden` 启动一次，检查 Engine 就绪，等待总计不超过 60 秒；不要循环启动，不更改系统设置或服务配置。Engine 不就绪准确写环境阻塞，继续能力文档，不反复浏览器/模型尝试。

Engine 就绪则核对固定 project `insightflow-acceptance-local` 的已有五容器、三个卷、运行端口 29384。只按已保存无损恢复流程启动既有容器；异常 ID/卷漂移或 unhealthy 不做全栈 up。按 6F3F21 约束可仅刷新 Frontend（旧镜像回滚标签、--no-deps、不变更其余四容器/卷），补部署版截图和 health/favicon 验证。Compose 文件/env 由旧 acceptance 中既有命令定位，不打印配置/凭据。

有安全登录 helper 和正确模型/tool 配置后，执行 6F3F20 唯一一次欢迎卡片“小惊喜”真实用户提交；不得多次模型重试。恢复安全登录及请求等待逻辑依照旧 runner，勿打印 cookies/keys/model正文/HTML。无凭据则报告所缺信息，禁止重置账号。固定栈/模型不可用不以 mock 冒充完成。

## 当前能力证据文档（必须完成）

核对当前源码、配置模板及已有 acceptance，不以老架构目标当现状。列出：
- 继承上游并保留的 LangGraph Lead、task 子 Agent/有限并发与隔离/取消预算、工具调用、MCP 与耐久异步任务、Skills、Local/AIO 沙箱、DeerMem 记忆、上下文压缩、规划/澄清、SSE、checkpoint/运行事件数据库持久化、Scheduler、认证/owner 隔离、可观测/receipt/guardrails。
- InsightFlow 新增/改造的 App/Harness 分层、Analytics domain/application/infrastructure/agent/api、SQLGlot 策略/语义授权/只读 PG/MySQL/限额超时/审计/evidence/报告复核、可信 analysis kind + fail-closed admission + 固定工具集 + run-scoped writer + owner artifact、安全轨迹投影、受控工作台、产品裁剪及新黑洞首页。
- 专职五角色 Agent 是目标，当前通用子 Agent 角色扮演与报告 writer/Reviewer 的实际机制要依据代码明确区分；RAG/vector retrieval 非现行目标；删除的 Custom Agent 管理不等于删除 task 委派。
- 每行写源码链接/关键符号、归属（上游保留/二开新增改造）、实现状态、真实验收范围。不要为了“主流功能齐全”添加无关功能。

修正 README 或旧架构说明中已经被 6F2 批准边界取代的“所有 MCP 强制同一 SQL 策略/AS-14 universal mediation 必定发布阻塞”现状表述：第三方 operator MCP 明确独立于平台 Analytics policy，AS-14 按批准范围已验收，仍不承诺任意 MCP 安全；目标架构可以保留但必须标目标。只改相关段落，不批量重写文档。

给最多 5 项风险排序的剩余门槛，区分已实现/缺验收/阻断个人简历演示与否，并给可直接使用、不过度承诺的简历描述。Phase 5 文件数量、全发布仍非完成；不扩展自动裁剪、不删除安全测试。

V0 文档回读/diff，生成脚本 Ruff 为定点静态检查；如环境可用，V3 仅上述一条真实用户旅程与受影响服务部署。主会话在实施期间等待。返回准确检查、实际文件/容器改动、截图、阻塞与能力摘要；不提交、不 push。约每 60 秒发送实际进展。

## 主会话独立复核后的文档修正（2026-10-07）

部署桌面/手机截图已由主会话目视接受；主会话只读确认五容器 running、三项 health healthy、`/health` 与 favicon 200。相应 acceptance/PROGRESS/current-capabilities 中“部署待主会话复核”现已过时，更新为明确已独立复核，整体发布仍 In progress。

能力清单的五角色请与既有设计表一致：Lead、SQL Analyst、Data Analyst、Reviewer、Report Writer。Metric Service 是服务，不另把 Planner / Metric 拼成五 Agent。主会话已核对 Lead 禁用 flags、Reviewer 同模型有界零工具实现、Gateway writer 路径能力。

独占新增文档修正范围 `docs/architecture/architecture-refactoring-report.md`：其94/219/357附近仍把 universal MCP mediation 写为现行发布阻塞，181/193附近仍用 skill 的目标扮演描述可信分析现状。只改相关事实段：引用6F2批准范围；普通聊天支持task，可信分析固定三工具；run-scoped writer/有界Reviewer 已实现，专职Agent角色链未实现。保留标明目标的未来设计，勿重写其余章节。6F3F21“未运行生产构建”应限定初始本地验证阶段，注明随后部署镜像内真实production build成功。

仅 V0 readback/diff 与文档引用检查；无需重跑应用测试、部署或模型。立即返回收口结果，不启动新验收切片。主会话正等待用户明确简历演示/完整发布的验收边界，后续任务由主会话分派。
