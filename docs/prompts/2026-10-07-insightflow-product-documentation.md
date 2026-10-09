# InsightFlow 产品身份、前端文案与公开文档收口

执行者：用户指定 `gpt-6-luna` / max。用户最新要求：项目产品定位为个人开发维护的 InsightFlow，README 与相关文档写好，前端不要出现 DeerFlow 品牌。此任务插入完整发布计划，完成后继续 AS-01～15；不替换最终验收目标。

## 不变量与独占文件

主会话已独立读取 LICENSE：MIT 要求保留原版权与许可声明，因此**不修改 LICENSE 既有声明，不删第三方包/资源法律署名**。产品可用独立 InsightFlow 品牌，不在产品介绍中反复展示原项目；不能新写“所有代码独立原创/零依赖/从零自研全部框架”的虚假声明。源码包名 `deerflow`、DEER_FLOW_* 配置键、磁盘路径、已有 API/容器协议保持，不能为文案机械改名破坏运行。用户指令覆写旧 BrandingTranslations 中“派生说明必须保留”的展示约定；将该过时注释/字段用途一起调整。

本切片独占：
- 根五份 README（md、zh、ja、fr、ru）、Install.md、CONTRIBUTING.md、必要SECURITY/RELEASING中产品品牌段落；不批量改版本历史CHANGELOG。
- docs/current-capabilities.md、docs/LOCAL_TRIAL.md面向产品的说明；新增 `docs/architecture/insightflow-overview.md` 写当前架构，并让README链接它。只修当前文档的产品文字，不改历史acceptance/prompt/ADR/UPSTREAM.md里的事实/源路径/tag。
- 前端 Footer 与 i18n 词条（analytics与根en-US/zh-CN）、相关landing/brand定点测试、必要页面metadata/用户界面官方站点/仓库外链。只清产品可见品牌，保留协议名称/机器字段。
- 新报告 `docs/acceptance/2026-10-07-insightflow-product-documentation.md` 和PROGRESS的本轮状态。

现有黑洞视觉代码/资产已验，不重做设计，不动Canvas。固定29384栈保留；刚创建AS01隔离栈29385保留供后续诊断。主会话等待你的实施，不做并行仓库工作。无需用户再确认，先不commit/push。

## 文档内容要求

1. README以 InsightFlow 为主，说明个人维护的受控经营分析工作台、具体用途和问题→目录/口径→查询治理→evidence/复核→报告链，架构/技术栈/功能/本地与Docker启动/安全边界/当前发布状态。中文为主要维护内容，其他语言保留对应语言、内容一致。不写已完成专职五角色、RAG、动态PII脱敏或完整发布通过。
2. README与公开介绍不含DeerFlow/ByteDance产品名或派生营销段落；许可证段简单“MIT，详见LICENSE”。仓库链接固定 https://github.com/zgozh/InsightFlow，clone示例用该仓库，问题/贡献链接不要再去原仓库。
3. Install.md 当前仍是原repo clone/setup instruction，改为当前InsightFlow实际可执行步骤（Windows/本地/默认四容器/配置模型与secret/initialize）；不承诺自动写入未提供key、不虚构命令。
4. CONTRIBUTING.md改个人项目贡献约定、真实根/module命令、中文注释/i18n、比例验证、配置不提交、版本两源和CI适用门禁。不要照搬旧产品功能或外部社区入口。
5. 新当前架构说明用模块化单体/App-Harness/Analytics五层、Gateway runtime、三工具固定边界、普通chat委派/MCP/skills与可信analysis区别、SQLite/Redis/default四服务、外部PG/MySQL、owner/持久化/Scheduler及真实限制。可用简短Mermaid图。准确当前实现，不用新文档替代历史证据。
6. current-capabilities 改成“当前功能与架构”产品语气，保留源码/验收范围链接与真实限制。用户可见表不再以“上游保留/二开新增”分组；可分类为“通用运行时/InsightFlow分析应用”。简历可称个人维护与核心架构改造，不虚构从零作者身份。符号链接保持真实。
7. LOCAL_TRIAL保留真实配置命令/路径/旧容器隔离记录，品牌正文改InsightFlow；实际脚本输出与旧project名不能伪造，把旧栈描述为“其他既有栈”，必要机器字面值以code保留。

## 前端与部署

页脚“源于开源/派生/原作者”介绍改成克制的 InsightFlow 产品维护说明与MIT/版权文字，继续可见EHT credit与许可证。全前端**用户可见字符串**检查原品牌：包括语音提示、官方站点tooltip、GitHub菜单，改InsightFlow或直接对应功能，不改第三方代码/类名。页面外链仅项目仓库或必要科学资源，不新增虚构官方网站。metadata和登录/工作台品牌保持InsightFlow。

V1/V2：受影响文件ESLint/Prettier、typecheck、品牌/i18n定点测试、landing相关Playwright（需要DOM变化才相应调整）；产品文字修改不要求全前端suite/build。文档V0回读、相对链接和代码命令检查。生产部署实际需要frontend镜像build，只在定点验证通过后做一次frontend-only build/up：保留旧image回滚tag，确认固定29384项目原五容器、三卷、端口不变；其余四服务不重启，不发模型请求。若原栈因Engine重启仍exited，不自行重复此前被拒绝的Gateway/Frontend/Nginx启动，可报告需要用户手动恢复；继续源码/本地检查而不绕过主机策略。

部署或本地最终桌面/手机截图供主会话目视确认页脚无旧品牌、黑洞未变、credit在；提供全部改动/准确命令/结果/残留机器与法律声明位置、未验证项。每约60秒发简短实际进度，足够上下文后立即实施，不做全仓历史搜证或长包装runner。交付后冻结，由主会话独立审查自动派后续AS15页面阻塞定位。
