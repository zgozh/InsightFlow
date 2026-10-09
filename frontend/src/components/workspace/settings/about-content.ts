/** 「关于」页的产品说明内联为 Markdown，避免构建器对 raw-loader 的依赖。 */
import { APP_VERSION } from "@/version";

export const aboutMarkdown = `# [About InsightFlow ${APP_VERSION}](/)

> **受控、可复核的经营分析工作台**

InsightFlow 由个人开发者持续维护，面向需要明确数据口径、访问边界和结果依据的经营分析场景。

工作台围绕数据源与指标登记、授权查询、审计记录、分析轨迹和报告发布组织。分析工具只访问平台
准入的资源；普通聊天、运维配置的 MCP 与技能属于不同的运行路径，不继承 Analytics 查询治理保证。

## 许可证

InsightFlow 按 MIT License 发布。完整许可条款与保留的版权声明见仓库根目录的 [LICENSE](https://github.com/zgozh/InsightFlow/blob/main/LICENSE)。
`;
