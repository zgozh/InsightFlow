# AS09 分析阶段前端投影与持久回填

实施gpt-6-luna/max。先读frontend AGENTS、已冻contracts/analysis-stage.v1.json与路由取证记录，按rg定位实际useThreadStream/ChatPage/run events API。后端worker正实现producer，不读取其未冻结修改做假设，双方只依赖下面固定协议。

## 所有权

frontend core/analytics 的types/schemas和最小stage状态helper、新stage panel；core/threads/hooks.ts与必要API/types；components/workspace/chats/chat-page.tsx、analytics中文/英文i18n；直接相关tests、frontend/AGENTS.md、独立记录docs/acceptance/2026-10-08-analysis-stages-frontend.md。不改backend、合同、黑洞首页、subtask状态或其他人员文件。

## 固定合同

Live为SSE `custom`，onCustomEvent得到完整payload，type=analysis_stage，按JSON合同strict Zod解析；extraSQL/rows/freeerror字段也必须拒绝，不直接显示未验证object。

永久GET /threads/{thread_id}/runs/{run_id}/events仍返回RunEventRecord，analysis记录 `event_type="analysis.stage"`、`category="analysis"`、`content=""`、`metadata=<同一完整payload>`。record.seq为分页thread-global游标；metadata.seq为阶段per-run游标。不期待data字段，不改endpoint。回填同样strict验证且run_id必须匹配请求与record scope。

按(run_id, metadata.seq)去重并有序合并live/历史，重复幂等，冲突同key不覆盖已接受可信状态；thread切换/新run清除当前临时状态，不能把其他run阶段串到本run。每run最多128条，按真实同stage running/terminal展示最近状态。不借SSE Event-ID当stage序号；gap后从持久events回填，而非把gap当完成。

只analysis模式开启阶段UI与回填；复用ChatPage，不塞Subtask/ChainOfThought状态，也不展示CoT。组件简洁使用现有tokens，中文主文案，en-US同步。阶段名/状态/稳定code本地译文，无SQL/原始行/provider错误。已知时展示duration/rows/bytes/risk/token观测，unknown usage不假造零、cached显式标复用。

刷新已有analysis thread后，使用已有runs API找到对应最近run并从永久events按实际分页合同回填。请求总量有界（最多20页/2000条原run events），只保存合同内128条，不拉全历史；前端API沿用既有认证cookie/owner错误处理。活跃run以实际stream metadata run_id绑定，malformed/foreign event忽略且不输出敏感日志。onFinish/onError/cancel与gap触发必要回填，run真实终态供显示解释，但不能编造后端stage成功。

## 验证

V2：shared hook+协议，定点schema/reducer/panel/hooks测试与frontend typecheck、受影响ESLint/Prettier即可，不整仓unit、不构建、不改依赖。测试保护真实合同：额外/错字段及foreignrun拒绝、live/replay重复与排序、thread切换、分页游标区别、gap回填、failed/blocked/cancelled、unknown tokens、普通聊天不启用、组件可访问与译文齐全。

先完整slice后一次检查，确认fixture失败窄修，保留已通过证据。禁止调用模型/容器或读取真实账号资料。完成冻结返回实际文件与准确命令结果；真实部署SSE/刷新验收会在后端冻结后的统一构建里做，不声称AS09已经验收。
