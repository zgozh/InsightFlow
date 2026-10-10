# 项目说明文档润色

实施者 gpt-6-luna/max。用户要求 README 与直接引用的主要文档表达更自然，减少模板化和机械语法。目标是改善可读性，不承诺任何 AI 检测分数。

## 文件所有权

只修改 README.md、README_en.md、Install.md、docs/current-capabilities.md、docs/architecture/insightflow-overview.md、docs/acceptance/2026-10-09-final-delivery.md、docs/acceptance/acceptance-scenarios.md。读取适用 AGENTS.md。其余验收证据、历史试用、法律归属、开发 Agent 指南不批量改写。没有润色必要的文件可保持不变。

## 修改要求

- 像作者写给使用者和开发者的正式项目说明，讲清用途、具体操作、架构原因；少用“串成一条可检查路径”“按批准范围”“主体/有界/受限合同/门禁”等抽象词堆叠。技术文档必要术语保留并解释，不用夸张企业级宣传。
- 中文 README 默认，英文版保持对应内容、自然英语。删除README中过长的模型/镜像编号、Root/子Agent工作流、历史失败测试统计等实施流水账，将验收细节留在证据文档，通过简短状态与链接指向。不能把未核验CI写成通过，也不能改写历史验收事实。
- 清晰区分 Docker 默认四容器（Nginx/Frontend/Gateway/Redis）、make dev三个应用进程、附加业务数据库的演示栈五容器。2026/29384默认与本机演示入口区别明确。不要为文档改部署方案。
- 保留全部必要部署模式、启动停止命令、Windows步骤、模型配置、SQLite应用库与外部业务PG区别、管理员初始化/普通用户授权、真实Agent设计和安全限制。不改可执行脚本/代码/配置/锁文件。
- 用户确认保持当前多容器架构，要求没有 make 时也能照着部署。核对 scripts/deploy.sh 的实际前置要求、配置初始化、构建启动、入口和停止保留数据行为，在 README 给完整短流程，在 Install 给 Windows/Git Bash 详细流程；make 作为可选封装。
- README 按介绍、功能与具体操作、架构、部署、首次使用与授权、常见问题、详细文档组织。中英文信息一致；技术细节归专门文档，避免重复长段落和流水账。真实页面路径和会话列表范围按源码确认。
- 保留许可证、第三方署名、来源记录与稳定代码标识，不机械替换包名。项目面文案以InsightFlow为名。
- 不添加虚构数据/截图/性能保证。查到现有文档明显自相矛盾时以已知源码/本次既有验收证据核实最小范围，指出具体修正，不扩展新功能。

## 验证与交付

V0：读回与实际diff审查、仅这些文件Markdown相对链接检查、git diff --check。检查中英文关键信息与命令一致，不运行应用测试、前端构建、Docker或模型请求；不扫全仓。
完成后冻结，返回实际修改文件、改写要点、具体检查结果。暂不commit/push，由主会话独立审查后执行既有授权交付。

## 独立审查补充

README 的功能表须列出 `/workspace/chats/new`，并简明交代通用 Lead、工具/task 子 Agent、MCP/Skills、沙箱、Memory、checkpoint/SSE 的配置启用条件，与受控分析固定角色区分。首次使用给编号操作步骤及经营问题示例，不虚构查询结果。模板复制说明仅供首次初始化，已有文件不要覆盖；模型配置不要暗示不存在的 enabled 字段。只补主说明，保持文档差异有限。

## 审查后提交

主会话已独立审查实际差异、README中英文与安装步骤，并核对 deploy.sh 的容器/密钥/readiness 行为，接受 V0 文档证据。按用户此前的 commit/push 授权，正常提交并推送本轮六个已修改文档与本实施说明，验收场景未改无需纳入。正常 hooks，不跳过门禁，不额外执行应用测试或构建。保护 uv.lock；必要时仅作用域内设置 UV_NO_CONFIG=true、UV_DEFAULT_INDEX=https://pypi.org/simple、UV_NO_SYNC=true 并恢复。当前 .git 写入和远程网络可能需主机审批，应按工具规则请求 require_escalated，不绕过拒绝。核对提交内容、本地远程 HEAD、干净工作区；CI未查询不声称通过。
