# Phase 6F3D2：显式报告请求的单次真实彩排与结构化采证

你是 InsightFlow 的执行调查员。先读 `.reviews/phase-06f3d1-report-chain-root-cause-audit.md`、`docs/acceptance/phase-06f1-real-analysis-rehearsal.md` 和 6F3C3 报告的限制段落。用户已授权临时管理员真实登录、演示后清理，并要求只有其明确说“暂停”才暂停整体任务。6F3C3 的唯一 run 成功但未采集 query/writer/Reviewer 的安全结构化证据；本轮是**新的一次**明确要求持久报告的合成样例，不是重试同一模型请求。不要触碰仍待用户手动清理的 `.reviews/phase-06f3c3-home-r26a9c2e`，也不碰旧 `insightflow-analytics-demo`。

## 启动前：隔离与可彻底回收

使用全新唯一 Compose project、唯一容器名、独立 network、PG/Redis 卷、loopback host port；复用已有镜像和真实私有模型配置，不打印凭据。**本次应用 home/SQLite/artifact 也必须位于该项目专属 Docker 命名卷，不得再绑定 Windows `.reviews` 目录**。只在 Git 忽略目录放不含凭据的临时 Compose override/脚本。先渲染 `docker compose config` 并逐项核对 volume source/target、应用 SQLite resolver 的最终路径、端口/容器名/网络，与旧 6F1 及上次残留目录没有共享或覆盖。若 Compose 合并规则导致 host bind 不能被可靠替换为命名卷，或数据库/凭据映射不明确，在任何创建动作前报告；不得先启动再猜。

## 唯一业务 run

五服务健康后，通过 NGINX 正常 `/setup`、重新 `/login` 建立短生命周期临时 admin；随机口令只存进程内存、不落盘/日志/命令行。由它通过合法管理 API 创建自己拥有的合成 PostgreSQL datasource、schema 与仅对此 principal 生效的最小 active policy，不改原项目的任何对象。正常创建 `kind=analysis` thread。向 Lead 发送**明确要求保存 Markdown 分析报告**的简短合成订单汇总需求（例如按 region 汇总合成金额，并引用受控查询证据）；避免只要求聊天答案。模型名精确 `deepseek-flash`。最多一次模型驱动 Gateway run，不为了得到期望结果重试。

**在结束进程/注销会话/拆除项目之前**，以已有 owner 会话读取该 run 的现成 SSE/history 或 owner-checked messages，并在进程内将内容投影成安全白名单：工具名及次数、`query_business_data` 稳定 code/是否带 evidence、`write_analysis_report` 稳定 code 与允许的 reviewer reason、run 终态。读取报告列表时分别记录 HTTP 状态、数量、是否存在同 thread/run 的 `published` 项；若存在，验证 owner artifact GET 200 与异 thread 404。只输出白名单元数据和哈希，不输出/保存模型消息原文、原始 SQL、结果行、报告正文、Cookie/JWT、密码、API Key 或 DSN。若无法安全投影某一字段，记为 unknown，不因它阻塞已有的其他证据采集；不得把 `run success` 当成报告成功或 `report_published=false` 当作索引为空。

## 结束与验证

按新项目 label/创建前清单精确核验后，只对该新 project 执行 `down --volumes`；确认其容器、网络、PG/Redis/**app-home** 命名卷全为 0，临时管理员随独立 SQLite 卷消失。旧 6F1 project 容器/卷状态不变；上次残留的 `.reviews/phase-06f3c3-home-r26a9c2e` 状态照实记录，不尝试删除或打开。

本轮 V3 只包括 Compose 渲染/健康、一次真实登录与 run、现有结构化读取、报告/权限读取、精确回收；不跑全量 pytest、前端套件、Reviewer 直连探针或额外模型 run。若发现具体产品缺陷，记录首个稳定失败点并回收，不现场修改生产代码。脱敏报告写入忽略的 `.reviews/phase-06f3d2-instrumented-report-live-rehearsal.md`，含实际请求/run 次数、通过/未通过/未知边界及清理读回；无实现提交。完成后交回 GPT 审查，由 GPT 决定下一切片。
