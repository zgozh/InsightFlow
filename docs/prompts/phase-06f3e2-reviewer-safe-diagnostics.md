# Phase 6F3E2：Reviewer unavailable 的安全阶段诊断

你是 InsightFlow 的实施者。先读 `.reviews/phase-06f3e1-reviewer-unavailable-root-cause.md` 与直接相关的 `reviewer.py`、`reports.py`、Lead 绑定调用。6F3D2 唯一真实 Gateway run 已证实 query evidence 与 writer 调用，writer 返回 `analysis_review_unavailable`；直接 Reviewer HTTP 200/approved 是另一次调用，不能据此判定本 run 的原因。此任务的目标是**定位真实失败阶段**，不得先放宽 Reviewer、增加重试或猜测修复。

## 一个最小、可保留的诊断切片

在 Reviewer 的既有失败分支记录服务端内部**稳定阶段类别**，足以区分：capability/身份不匹配、Lead 模型绑定失败/未绑定、输入形状/序列化失败、Provider 异常、超时、严格响应解析失败。可用一个简短私有 helper 或相邻稳定日志；按既有代码风格选最少改动。日志只允许事件名、固定阶段枚举和不含凭据的 opaque `run_id`；禁止记录 exception 文本/traceback、prompt/response、SQL、rows、报告正文、token、DSN、账号/凭据，不改变 ToolMessage、HTTP 响应或审计契约。成功/拒绝路径只在确有定位价值时记录，不造新 tracing 系统、配置开关或持久表。Lead `bind_lead_model()` 的布尔结果不可继续静默丢弃；失败仍 fail-closed，仅产生同一安全类别。保持原有 20 秒限时、零工具、同一 server-selected base model、256 输出上限、一次初审最多一次修订、严格 JSON 和既有外部稳定码。

验证级别 V2：一个直接相关的定点回归测试验证至少“绑定失败”和“调用/解析失败”的阶段可区分，且 caplog 不含注入的异常/输入敏感样本；再跑受影响的 Reviewer/Lead 定点测试与对应 Ruff check/format、`git diff --check`。不跑整仓/前端/Playwright。生产代码与测试形成**一个独立提交**；不改模型工厂、配置、依赖或 lockfile。若无法不泄漏敏感内容地定位类别，停止报告备选方案，不先写冗余防御层。

## 一次真实确认

定点验证通过后，按 `docs/prompts/phase-06f3d2-instrumented-report-live-rehearsal.md` 的已验证隔离方式创建**全新** project：Gateway app-home/SQLite/artifacts、PG、Redis 全为该 project 专属 Docker 命名卷，旧 6F1 与仍待用户手动删除的 `.reviews/phase-06f3c3-home-r26a9c2e` 均不碰。复用已验证的 setup/login/API 输入格式和镜像；若 Gateway 诊断代码需新镜像，只构建本项目使用的 Gateway 镜像，不重建不相关服务。显式请求持久 Markdown 报告，最多一次模型驱动 Gateway run。记录 writer 稳定码及**同 run ID 的阶段枚举**，不输出原始日志或敏感 payload；若报告发布，验证 owner artifact GET 和异线程拒绝；若失败，停在该稳定阶段，不重试模型 run。

无论成功失败，按精确 project label 只对新 project `down --volumes`，确认容器/网络/app-home/PG/Redis 卷均为 0，旧项目状态不变。报告写入 Git 忽略的 `.reviews/phase-06f3e2-reviewer-safe-diagnostics.md`：文件范围、定点门禁、真实 run 次数、阶段类别、报告/权限结果、资源清理及未验证项。不要把外部 ToolMessage 的 `analysis_review_unavailable` 自行改成更细的内部原因；完成后交回 GPT 复验并停在此切片。
