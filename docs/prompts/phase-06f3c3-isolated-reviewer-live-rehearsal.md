# Phase 6F3C3：全新隔离 Compose 上的临时管理员彩排

你是 InsightFlow 的执行调查员。先读 `docs/prompts/phase-06f3c2-temporary-admin-live-rehearsal.md`、`docs/acceptance/phase-06f1-real-analysis-rehearsal.md` 与 `.reviews/phase-06f3c-fix-01-deepseek-reviewer-token-field.md` 的相关段落。6F3C2 的只读结论已确定：现有 `insightflow-analytics-demo` 中跨 owner 给临时管理员授权被正确拒绝，临时 datasource 又无物理删除接口；**没有创建账号或写入应用数据**。因此本切片改用一个全新、一次性的隔离 Compose project，不更改 6F1 项目或其卷。用户已授权模拟临时管理员真实登录并在演示后清理该账号。

## 前置隔离门禁（任何创建动作之前）

验证当前 `main` / 干净工作树 / `be7516e` 祖先与 Docker daemon 健康。选择唯一项目名、唯一 loopback 入口端口和唯一应用 home，三者都不得与现有 6F1 或任何其他项目重合；本次临时文件只放 Git 忽略的 `.reviews/` 下。仅用临时 Compose override 解决现有 overlay 固定 `container_name` 的冲突，不改仓库 Compose、配置模板或生产代码。先 `docker compose config` 渲染并检查服务容器名、所有 `volumes`/bind mounts、network、host ports、`DEER_FLOW_HOME` 以及应用 SQLite 实际路径：**必须证明新 app DB、新 PostgreSQL 合成数据卷、新 Redis 卷都不共享 6F1 的路径/卷/容器/端口**。确认 init SQL 在新 PostgreSQL 卷上会产生同一合成样例，且新项目能获得现有私有模型凭据但不回显值。若任何一项无法只读证明，停止在变更前报告，不猜测启动。

## 单次真实链路

隔离条件成立后，只启动此唯一临时项目；优先复用已构建镜像，避免为本次彩排重跑不必要的前端/后端构建。health 通过后，**经 NGINX 的正常 `/setup` 与登录路径**在新应用库创建唯一临时 admin；临时随机口令仅在进程内存，不能出现在命令行、日志、聊天、报告或文件。由该 admin 通过合法管理端点创建**仅指向新项目合成 PostgreSQL** 的 datasource 与精确 active policy；其 owner、principal、secret_ref 与数据源配置由服务端规则决定，不绕过 Query Policy、不直写授权表、不借用 6F1 旧 owner。

随后最多发起**一次模型驱动的 Gateway analysis run**：认证 → 持久 analysis thread → `inspect_business_catalog` → `query_business_data` / 同 run evidence → 内部 Reviewer → `write_analysis_report` → owner artifact GET；另核对跨线程/主体读取拒绝及安全轨迹的 Reviewer 稳定状态。记录 HTTP 码、稳定决定码、计数、哈希和是否完成，不记录 API Key、口令、cookie/JWT、原始 SQL、结果行、DSN、报告正文或模型自由文本。Reviewer 直连请求已在 6F3C Fix 01 真实通过，不重复单独探针。若链路失败，停在首个明确失败点，不重试模型 run、不现场修改生产代码。

## 精确回收（成功或失败均执行）

先留存不含敏感内容的验收证据，再停止**本次新建 project**。只对已由 project label 和创建前资源清单确认归属的新容器、网络、命名卷执行 Compose `down --volumes`；不得删除 `insightflow-analytics-demo` 的任何资源，也不得执行 Docker 全局 prune。唯一新建 app home 必须先解析绝对路径并确认严格位于本次 `.reviews/` 临时目录内，再按该精确路径清理；不得对 workspace 根、`D:\`、`$HOME` 或未验证变量做递归删除。最终只读确认新项目的账号数据库、容器、网络、卷和 app home 均不再存在，而 6F1 原项目仍保持其原有 5 个容器/2 个卷且健康。**清除新项目的应用库即清除临时 admin**；不要到旧项目里单独删账号。

## 验证与交付

验证级别 V3，但仅是这一条真实集成彩排：Compose 渲染/health、一次业务 run、owner/非 owner 读取、资源回收读回；不跑全量 pytest、前端套件或重复 6F1/Reviewer 门禁。不修改生产代码、测试、配置模板、lockfile，不提交临时 override 或凭据。报告写到忽略的 `.reviews/phase-06f3c3-isolated-reviewer-live-rehearsal.md`，列出前置隔离证明、运行阶段状态、模型/run 次数、Reviewer 结果、清理后读回及未验证项。若项目启动或回收无法保证，只报告安全的实际状态，不扩大删除或宣告整体 Phase 6 完成。交回 GPT 复验后停在此切片；整体任务仍按用户要求持续推进，只有用户明确说“暂停”才暂停。
