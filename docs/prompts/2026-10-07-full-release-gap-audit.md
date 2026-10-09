# 完整发布验收：差距与实施接口盘点

执行者：用户最新指定 `gpt-6-luna` / max。工作目录 `D:/develop/workspace/InsightFlow`。

## 用户验收边界

用户已明确选择完整发布版，完成现有 AS-01～AS-15 全部验收，并要求后续用 Luna max。首页黑洞6F3F21本地与部署已由主会话代码/截图/health独立接受；6F3F20唯一真实普通聊天run成功、write_file/present_files调用和结果各1、HTML持久预览，点击交互变化仍未证实，不再重发这个示例。主会话后续按方案→实施证据→独立审查→下一切片持续推进。

## 当前环境与冻结工作

已有UI/README/能力文档和acceptance未提交，保留所有现有diff。普通本地Next dev仍可用3000；固定Docker `insightflow-acceptance-local` 五容器在运行，PG/Redis/Gateway healthy，Nginx loopback29384，新Frontend已部署。原三卷不能删，现有用户/会话/业务数据不能清理或覆盖。Docker启动原Gateway/Frontend/Nginx曾被主机自动审批拒绝，用户已手动恢复；不绕过任何新审批拒绝。不要修改全局配置、打印secret/私密自由文本，不push。

## 本切片独占与交付

只写 `docs/acceptance/2026-10-07-full-release-gap-audit.md`。不修改生产代码、不新增测试、不改现有契约，不提交。V0 回读/相对链接检查/diff。本切片只做一次有界证据收集：复用已读模块资料，不全仓历史扫描，不跑测试或模型，不启动/停止容器。主会话在你工作时等待。

先读根AGENTS、backend/AGENTS、目标子目录AGENTS、`docs/acceptance/acceptance-scenarios.md`、`phase-06d-contract-reconciliation.md`、`phase-06f2-as14-boundary-evidence.md`、`docs/current-capabilities.md`。只按每个缺口读取必要代码/测试符号；旧ADR是历史，不把旧 universal MCP requirement重新当当前批准边界。

报告为主会话的后续实施计划提供以下具体材料：

1. AS-01～15逐条：当前实现/缺失行为、已有效证据、仍需的具体输入与期望输出、对应当前文件/符号/测试ID、建议验收命令；区分缺实现与缺真实验收，不把全部标成待开发。
2. 优先钻取AS-07/08/09/10：当前固定三工具、Lead flags、Metric Service/lookup有无、evidence快照、Reviewer capability、writer及trace接口。标明能否在**保持模型schema/最终分发仍恰好三工具、普通task/MCP/bash仍禁用**的前提下，通过App-owned、服务器固定内部角色调用补齐Lead/SQLAnalyst/DataAnalyst/Reviewer/ReportWriter角色链；需要的新接口/文件与既有可复用机制。不得把角色标签、prompt扮演或工具函数重命名当成多个Agent已实现。只给代码证据和建议接口，架构裁决归主会话，不自行修改契约。
3. AS-01具体多主体认证/管理员创建和删除临时用户的HTTP入口/契约、现有safe DPAPI helper可复用位置、如何只建本切片标识的临时对象并精确清理；若不能安全清理，列明限制，不动现有真实账号。
4. AS-02/03/06真实数据库脚本/fixture如何复用PG16和MySQL8.4、只读角色、超时/row/byte风险预算证据。新真实模型run采用可核算合成数据，不重复普通小惊喜。指出模型非确定性与服务器控制应分开的断言。
5. AS-11/12/15：Scheduler是否支持持久kind=analysis，如何配置独立测试项目的PostgreSQL应用DB和默认四服务SQLite部署；给确切配置键、已有脚本入口、必需资源、隔离和恢复边界。不实际建立新项目，本轮不需要真实账号/模型。
6. 推荐3～5个可独立验收的实施里程碑及文件独占范围、依赖关系、V1/V2/V3检查。没有事实支持时明确“未证实”和需要查看的具体接口，不猜测实现/环境已具备。

返回报告路径、重要冲突/缺实现、下一个最小可实施切片建议。每约60秒发简短实际进度，完成后冻结；主会话会独立审查并自动派下一任务，不终止整体发布任务。
