# Phase 6F3F18：一次真实“小惊喜”浏览器验收

6F3F17 已证明：固定验收实例漏掉上游既有的 `write_file` 配置；补回后，单次 `deepseek-flash` API run 已调用 `write_file`、`present_files`，同 owner 的 HTML artifact GET 为 200。上游 `surprise-me` 技能曾在 Phase 5 删除，当前欢迎示例只是可编辑提示词；本切片**不**恢复技能或重写功能，只验证当前用户可见的“小惊喜”卡片→产物链。完成本切片后不要再围绕同一示例连续增加测试；转入 Phase 6 剩余验收清单排序。

1. 起点 `afc6763`；只读确认干净工作树、固定 `insightflow-acceptance-local` 的原五容器/三卷/`29384` 与热加载后的 `write_file`。不要重建/清理栈、删除既有试用会话或改配置。
2. 先用现有成功 run `6ce643e7-761c-4ba2-b110-97fdb8e380fa` 的 artifact 作**无模型请求**的受权浏览器预览检查：同 owner 登录后通过 UI 的正常产物入口打开，核对真实 HTML 可见且至少一个点击交互可用。只读，不改 artifact；若预览本身有明确缺陷，定位到最小边界后停止，不浪费新的模型调用。
3. 预览可用后，仅一次新的真实 Chromium 聊天流程：从欢迎页点击“创建一个小惊喜”，确认仅填入可编辑提示、不自动提交；把 `[主题]` 改成“星空”，选精确模型 `deepseek-flash`，再**显式点击提交一次**。使用异步 request/SSE/路由等待和有界完成等待，记录是否真的出现 `/runs/stream`、HTTP、`Content-Location`、thread/run ID；禁止复用 6F3F14 点击后同步查 0 再关闭的逻辑。若提交后未观测到请求，保持页面、按可证事实区分 UI/网络/认证问题，不重按提交。
4. 如果 run 建立，使用同一 thread/run 的结构化轨迹与 owner artifact 列表确认 `write_file`、`present_files`、虚拟路径、状态及前端产物入口；有 HTML 才验证 UI 预览内容与一次点击。模型未调工具时如实记录一次性结果，不擅自重复付费。只写安全摘要；原始模型回复、SQL、token、凭据、cookie、artifact 正文不得进入报告。
5. 本切片按 V3 **单条用户流程**验收，不跑全仓后端/前端测试、全量 Playwright 或无关构建。若定位出确切的局部代码缺陷，可做最小修复、直接受影响定点验证和最小服务刷新；修复前后模型请求总数要明确，且未经主会话重新裁决不得再发第二次模型 run。不要把已有 API 产物验证冒充新 UI 链通过。

将结果写入 `docs/acceptance/phase-06f3f18-surprise-browser-acceptance.md`，同步 `docs/PROGRESS.md`。提示词和证据一并提交，临时 runner/截图放忽略目录；工作树干净，不 push。末尾附一张**简短剩余验收清单**，按“必须验收 / 可登记残差 / 已有证据不重跑”分类，以便主会话下一轮切换焦点。停在主会话复验。
