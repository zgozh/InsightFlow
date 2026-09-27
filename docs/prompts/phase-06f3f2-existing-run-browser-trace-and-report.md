# Phase 6F3F2：既有真实 run 的浏览器轨迹与报告入口

> 执行者：现有 `gpt-6-luna`（max）。先读本文件、`.reviews/phase-06f3f1-real-trace-readback-and-contract-reconciliation.md` 和 `frontend/AGENTS.md` 的 Analytics 边界。不重做 6F3E10 的模型运行，不启动 5C。

## 目标和范围

6F3F1 已证明同 run 的公开消息可按现有纯函数投影 Reviewer 拒绝/通过，但**没有真实浏览器卡片或报告下载证据**。复用固定验收栈中的已发布 run `63cfc92a-97d9-446d-ad21-58d71ff97821`，在一个真实浏览器会话核对 owner 登录后的分析轨迹及报告入口。不得重新生成报告、发起模型请求、改数据源/策略或重建整个栈。

这是单用户主流程的 V3 定点浏览器验证，不是全量 Playwright 门禁。首选既有 Chromium/Playwright 与 repo helper；最多一次受控浏览器流程，若遇到确定性环境错误先最小定位，不能靠反复重跑同一失败命令碰运气。纯文档/ignored helper 按 V0；只有确认产品缺陷才改前端并做直接受影响的单测/定点 Playwright、类型和格式检查。无需全量后端、全量前端、数据库测试或新模型 run。

## 执行

1. 核对 HEAD 从 `8de9ab3` 继续、工作区干净、原 `insightflow-acceptance-local` 5 容器仍在。仅通过已保护的 DPAPI admin 在进程内登录；由报告索引确定真实 thread/path，不在日志中输出身份凭据、run 消息正文、原始 SQL、行、token 或 artifact 正文。浏览器状态/下载只存于 Git 忽略的临时目录，结束后安全清理**明确创建的临时文件**，不动固定容器/卷/网络和旧 6F1 项目。
2. 用真实浏览器访问该 analysis thread。观察固定、安全的 DOM 状态：分析轨迹面板实际出现；catalog/query/writer 步骤存在；`write_analysis_report` 的拒绝与通过状态按用户语言显示；evidence 只以摘要/安全计数展示；窄屏或需要展开面板时只做必要操作。只记录布尔值/计数/testid，不把整页 HTML、截图、报告内容或任意模型自由文本写入报告。若 UI 无法区分拒绝/通过，先确认同 run API/纯投影与页面绑定的具体断点。
3. 从 Web 的报告列表或轨迹产物入口找到这条 `published` 报告。验证用户可触达 owner-checked artifact 下载/打开路径（浏览器响应/下载事件与状态即可），不读取或保存正文。若现有 Web 只有返回聊天线程的链接而没有报告产物入口，确认这是 AS-10 的具体缺口；在当前前端架构内做最小可用链接/按钮，调用既有鉴权路由，不签发公开 URL、不绕过 owner check、不把 SQL/正文塞进 query key 或 trace。新文案中英双语，以中文为主，并补直接 UI 回归。
4. 若观察到产品缺陷，仅修已证实的当前路径问题，不重设计聊天页面、不新增第二状态源或通用适配层。前端镜像无源码挂载时只重建/替换原 project 的 Frontend 服务加载修复，不碰 Gateway/数据库/卷。最多再用**同一已发布 run** 做一次只读浏览器复核。若无法取得真实浏览器证据，说明具体原因与已有 API/DOM 替代证据，不能把它写成通过。
5. 更新 `docs/acceptance/phase-06d-contract-reconciliation.md` 的 AS-09/10 和 `docs/PROGRESS.md`，只按实际观察缩小残差；不因单例把整项 AS-09/10 标为 PASS，也不宣称任意文本或 artifact 正文绝无敏感内容。报告写 `.reviews/phase-06f3f2-existing-run-browser-trace-and-report.md`，列浏览器状态、所见安全计数、报告入口/下载状态、实际检查结果与未验收范围。若只改文档，一个文档提交；若有产品修复，产品/测试与文档可作一个独立实现提交。工作树干净，停在 GPT 复验。
