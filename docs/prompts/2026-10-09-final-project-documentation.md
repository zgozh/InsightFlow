# 最终项目文档整理

gpt-6-luna/max。用户要求InsightFlow个人开发企业级项目的完整中英文说明，默认README中文，仅两种语言，部署/启动/使用情况清晰，清理过时无用文档。产品文档不提上游品牌；法律LICENSE/版权/UPSTREAM来源及必要稳定机器标识保留，不能伪称底层全原创。已有README已重写但验收状态滞后。

独立所有权：README.md/README_en.md、Install.md/CONTRIBUTING.md/RELEASING.md/SECURITY.md、docs/current-capabilities.md、docs/architecture/insightflow-overview.md 与 docs/ARCHITECTURE.md、docs/LOCAL_TRIAL.md，以及 docs/acceptance/2026-10-09-final-documentation.md；允许这些文档中重复的过时入口合并后删除。根AGENTS只修改这些文档链接，不改变技术规范。其它生产代码/部署脚本/验收记录/prompts/PROGRESS/INTERRUPTION/法律文件只读。与两个真实验收worker完全独立。

先有界读取现有Makefile/scripts入口与默认compose/关键README，核对真实命令，不执行构建或应用测试、不读取真实config/env内容。写清以下**实际已支持**路径：

- 开发准备make config/install或Windows实际Python脚本等效方式、make dev及默认localhost入口；前端后端单独开发说明，配置前提与WindowsDocker建议。
- 本地生产make start/stop、SKIP_FRONTEND_BUILD复用条件；Docker生产make up/down与Docker开发docker-start/stop区别；默认4服务、127.0.0.1绑定、Redis必需、SQLite默认，external PostgreSQL app和business DB的配置区别与凭据server secret_ref。数据库恢复/升级须对应真实脚本，不编造。
- 先setup管理员→登记source/schema/policy→指标grant→普通B数据源/指标点分析预填可编辑不自动发送→报告/下载/审计/阶段→定时任务配置（当前scheduler.enabled需显式开启）。普通聊天与受控分析的工具边界、task/subagent/MCP/skills/checkpoint成熟底座准确说明，不加不存在RAG/PII动态脱敏/任意平台集成承诺。
- 常见空目录、401/403/404、模型/数据库配置与服务启动问题、安全凭据规则。介绍以能力和流程为主，不放大量中断日志/私人端口/失败过程在README顶端，验收证据链接到current-capabilities即可。项目当前报告正例已passed，API安全与预算/PGadaptertimeoutpassed，Frontend已经部署但两click验收pending，scheduler/restartpending；不能写最终全部通过。

清理范围：移除已废弃的多语言README残余链接（代码/测试的机器字符串不归你）；docs/ARCHITECTURE与overview/LOCAL_TRIAL若内容过时重复，选一个清晰当前架构入口与一份安装使用指南，合并有价值内容后删除真正重复文件并修引用。不要把所有历史plans/acceptance/prompts都重写或删除，它们是仍需复用的工程证据；不维护已移除Projects/IM/Browser/ManagedAgent使用教程。确认直接外链/内链路径。

V0：readback、你所改文档本地link target检查、git diff --check，不应用测试、不整仓brand替换包名、不commit/push。为文本采用apply_patch，不Windows长命令/模板文字。交变更文件/删除理由/精确checks后冻结，Principal最终等集成验收事实收口再commit/push。
