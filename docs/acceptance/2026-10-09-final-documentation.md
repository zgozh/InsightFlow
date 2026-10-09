# 最终项目文档收口

核对日期：2026-10-09。本记录收敛 InsightFlow 当前产品说明、安装与启动入口、架构链接和最新验收边界。只改文档，没有改生产代码、部署脚本、验收记录、法律文本或运行配置。

## 文档变更

- `README.md` 为默认中文介绍，`README_en.md` 提供英文对照。两页说明产品页面与管理员/普通用户流程、受控分析边界、服务拓扑、SQLite/外部 PostgreSQL 与业务数据源的区别、首次启动及当前验收状态。数据源与指标的两步预填标为已部署但仍待浏览器修复和验收；没有写成已通过。
- `Install.md` 是唯一的标准安装与使用指南，列出 Docker 生产、Docker 开发、本机开发和本机优化运行方式；补充 `SKIP_FRONTEND_BUILD` 的复用条件、Windows PowerShell 实际 Python 脚本和依赖安装命令、首次管理员/模型配置、经营分析操作、凭据边界及常见 401/403/404 和启动问题。
- `docs/current-capabilities.md` 与 `docs/architecture/insightflow-overview.md` 按最新验收记录更新：PostgreSQL 报告链、API/查询安全、风险预算和 PostgreSQL adapter timeout 已通过；两步预填、Scheduler 与重启/恢复仍待验收；Phase 6 和整体发布仍未完成。
- `AGENTS.md` 仅更新文档导航链接，没有改动服务、配置或验证规范。
- `docs/LOCAL_TRIAL.md` 改为历史本机试用与验收记录；删除重复的一般快速启动和配置说明，当前安装统一指向 `Install.md`。保留 6D2 专用 PostgreSQL 演示步骤及 6D1/6F1 历史证据，因为既有验收记录仍引用这些段落和启动/停止锚点。

## 删除与保留

- 删除 `docs/ARCHITECTURE.md`：其服务拓扑、模块边界、产品面与安全说明已收敛到 `docs/architecture/insightflow-overview.md`；版本发布细节由 `RELEASING.md` 维护，根目录和当前产品页没有继续指向旧文件的入口。
- 根目录产品说明只保留 `README.md` 与 `README_en.md` 两种语言；旧法语、日语、俄语及独立简体中文 README 不再作为产品入口。法律来源、`LICENSE`、`UPSTREAM.md`、版权署名及稳定机器标识保留。

## 验证范围

本变更按 V0 文档检查处理：回读 11 份所有权文档，检查本地 Markdown 链接目标、尾随空白和末尾换行；全部目标存在且文本格式检查通过。`git diff --check` 退出码为 0。没有运行应用测试、构建或浏览器验收；没有读取真实配置或环境文件。
