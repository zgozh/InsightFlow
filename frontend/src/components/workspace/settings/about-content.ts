/**
 * 「关于」页的 Markdown 内容。刻意内联而不是从 .md 导入：Turbopack 无法为 .md 解析 raw-loader。
 *
 * Phase 4 的品牌边界：产品名称改为 InsightFlow，并从用户可见内容里移除上游官网／仓库／问题反馈／
 * 支持邮箱与 star 导流；**必须保留**上游派生说明、MIT 许可证与作者致谢——那是归属，不是导流。
 */
import { APP_VERSION } from "@/version";

export const aboutMarkdown = `# [About InsightFlow ${APP_VERSION}](/)

> **受控、可审计的企业经营分析工作台**

InsightFlow 把"问一个业务问题"变成一条可追溯的链路：确认口径 → 查询可访问的数据目录 → 在平台的
受控查询通道里执行只读 SQL → 用 evidence 引用每一个数字 → 复核 → 交付带索引的报告。

它不是一个"什么都能干"的超级智能体，而是一个**有边界**的分析工作台：权限、成本门禁、行数/字节
上限、一次性执行计划与审计门禁都由平台侧执行，模型只能按顺序使用它们。

---

## 🧭 产品能力

* **数据源与数据模型**：管理员登记数据源、维护 schema 与访问策略；用户只看到自己有权限的部分。
* **受控查询**：每次查询都经过语法策略、语义授权、EXPLAIN 成本门禁与一次性执行令牌。
* **指标中心**：口径以版本化指标登记，退役保留历史。
* **审计历史**：每次计划与执行都留下稳定决定码、风险级别与计数，但**不记录**原始 SQL 或结果行。
* **分析轨迹**：从既有会话消息投影出结构化步骤与 evidence，不是模型的思维过程。
* **分析报告**：报告索引只登记"谁在哪个会话里发布了哪个文件"，打开文件仍要经过会话归属校验。

---

## 📜 License & Upstream

InsightFlow 基于 **DeerFlow v2.1.0-rc0** 深度重构，并遵循其 **MIT License** 分发。

DeerFlow (**D**eep **E**xploration and **E**fficient **R**esearch **Flow**) 是一个由社区驱动的
开源 SuperAgent harness。本仓库保留它的 MIT 许可证、上游版权声明与派生说明；完整许可证文本随
仓库根目录的 LICENSE 文件一同分发。

---

## 🙌 Acknowledgments

感谢那些让这一切成为可能的开源项目与贡献者——我们站在巨人的肩膀上。

### Core Frameworks

- **[LangChain](https://github.com/langchain-ai/langchain)**：支撑与大模型的交互与链式编排。
- **[LangGraph](https://github.com/langchain-ai/langgraph)**：多智能体编排与 checkpoint 语义的基础。
- **[Next.js](https://nextjs.org/)**：Web 应用框架。
- **[FastAPI](https://fastapi.tiangolo.com/)**：Gateway HTTP 层。
- **[SQLAlchemy](https://www.sqlalchemy.org/)** 与 **[Alembic](https://alembic.sqlalchemy.org/)**：持久化与迁移。
- **[SQLGlot](https://github.com/tobymao/sqlglot)**：SQL 解析与规范化。

### UI Libraries

- **[Shadcn](https://ui.shadcn.com/)**：界面基础组件。
- **[SToneX](https://github.com/stonexer)**：逐字视觉效果的贡献。

### Special Thanks

感谢 DeerFlow 1.0 与 2.0 的核心作者：

- **[Daniel Walnut](https://github.com/hetaoBackend/)**
- **[Henry Li](https://github.com/magiccube/)**
`;
