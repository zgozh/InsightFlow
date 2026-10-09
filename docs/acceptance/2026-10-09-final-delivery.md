# 2026-10-09 最终交付状态

本页汇总当前功能验收与交付门禁。`通过`限定于批准的验收合同，不代表任意输入、部署形态或第三方工具组合均已验证。

## 功能验收

按批准范围，功能验收通过。细项见[最终发布证据矩阵](2026-10-09-final-release-matrix.md)；AS-02 MySQL 保持批准的可选范围。

AS-11 的最新自动任务在 `server-computation1109` Gateway 上运行：新建的 analysis thread 没有历史 run，唯一一次 `once` occurrence 的 scheduler `attempt=1` 完成授权查询、Data、Writer、Reviewer approved 和 Publish，`run=success`、`task=completed`，生成 1 份 owner report 与 1 份 evidence。该次运行无重复提交，受控工具为 3 项且未调用 `ask_clarification`。

数值输出 `1200.50`、`1800.00`、`900.75` 与 `3901.25` 按两位小数、未知单位和本次 evidence scope 通过校验；报告预览、下载、附件与 artifact hash 一致。Data role 提交证据单元格引用和运算计划，Gateway 的 domain verifier 解析 evidence snapshot 并使用 `Decimal` 计算；计算值来自服务端代码，不依赖模型自行算术。Markdown 连字符解码和三个月 association 检查通过。

此结果只证明本次新线程和合同样例。早期失败 run、Reviewer 的 `fail-closed` 拒绝，以及额外授权和调用次数上限触发的拦截事件仍保留，不被此成功覆盖；不承诺任意自由文本或未来输入均通过。

其它组合证据包括普通聊天真实 HTML artifact、预填草稿 4 项定点测试和浏览器探针、角色/数字/报告/owner/privacy/policy/budget 检查、真实 HTTP timeout 与 audit、FakeAgent HTTP cancel 后 worker interrupt/thread idle，以及真实 PostgreSQL checkpoint/evidence producer hash 复用和新 Gateway 进程 unfinished-run 恢复。可按矩阵所列验收文档核对；不要求用付费模型 cancel 重复证明 FakeAgent 覆盖的取消机制。

## 部署与交付门禁

本次 AS-11 运行来自 `server-computation1109` Gateway。之后的 `29384` 原入口 rollout 已由独立后验收确认通过：首页 200、health/ready 200、匿名请求 401；当前 Gateway 为 `server-computation1109`、Frontend 为 `frontend365`。原 PG/Redis/Nginx 容器 ID 与 volumes 均保留，并创建包含数据库、WAL、SHM 的 52-file 完整备份。原 Apply 命令退出码未返回；不据此声称脚本 exit 0，结论依据是全部独立后验收通过。此处不公布公网演示地址、账号或凭据。

功能与部署门禁按批准范围均已通过：Windows 7 项门禁、合并后的 14 个适用候选检查、`sharedproxy=True` 独立复验（1 passed、6 条 deprecation warnings、16.75 秒），以及 29384 原入口 rollout 的独立后验收。Root 已接受最终源码与暂存审查。本记录截于发布提交前；commit/push 状态以 Git 记录为准，远程 CI 结果以 Actions 为准（本记录形成时尚未运行），不声称 CI 全绿。

最终暂存前一致性检查：`backend/pyproject.toml` 与 `frontend/package.json` 都是 `2.1.0-rc0`。`backend/uv.lock` 从未重新解析，已从验收镜像内读取的 canonical 文件逐字节恢复，SHA-256 为 `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`。受污染副本与 canonical 的 213 个包 name/version、依赖图和所有 artifact SHA 一致；差异包括 registry/download URL，以及 `defusedxml 0.7.1`、`jsonpatch 1.33`、`olefile 0.47` 三个包缺失的公开 artifact size/upload-time 元数据。已恢复 canonical 后，这些镜像差异不进入提交。

对暂存内容的高置信凭证模式扫描覆盖 296 个文本文件，未发现 private-key marker、常见 provider token、带凭证 URL 或长凭证赋值命中；3 个二进制文件未按文本扫描。所有目标改动已暂存并通过 Root 最后 staged review。本记录形成于发布提交前；commit/push 状态以 Git 记录为准，远程 Linux CI 尚未运行。

验收证据以本仓库链接的安全摘要和合同记录为准；被 Git 忽略的本机 `.reviews` 文件不是外部审阅的必要依据。
