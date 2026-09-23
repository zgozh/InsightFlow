# Phase 5B 续接提示词：Luna 从 B3 后接手

你是 InsightFlow（DeerFlow `v2.1.0-rc0` 硬分叉）的实施者。本轮只完成 Phase 5B 的遗留修复、B4、B5 和最终报告；不要启动 Phase 5C/6。GPT 负责架构裁决与最终审查，你负责实现和提供可复核证据。用户希望减少对话轮次：各门禁通过时自行继续下一批；遇到新增失败、越界或需要改变 KEEP 契约时立即停下报告，不要猜测批准。

## 先读权威输入

按顺序完整阅读根 `AGENTS.md`、涉及模块的 `AGENTS.md`，然后阅读：

1. `.reviews/phase-05b-handoff-to-luna.md`（断点、环境、已知陷阱）；
2. `docs/prompts/phase-05b-execute-removal-batches.md`；
3. `docs/architecture/phase-05-capability-contraction.md`；
4. `docs/removal/phase-05-deletion-manifest.yaml`、`phase-05-dependency-impact.md`、`phase-05-verification-matrix.md`；
5. `docs/superpowers/plans/2026-09-22-phase-05b-capability-removal.md`；
6. `docs/decisions/0002-phase-05-size-budget-reconciliation.md`、`docs/PROGRESS.md`。

文件里的详细删除清单、门禁和 Task 6 报告要求仍是施工主体。本提示词只裁定 B3 遗留及模型交接时的冲突；如与旧交接备忘的 `git commit --amend` 或 provisioner 待裁决表述冲突，以本提示词为准。仓库中的 `skills/public` 是 **InsightFlow 运行时技能**，不要与本机 Codex 个人 skills 混淆。

## 起点与保护边界

- 仓库：`D:\develop\workspace\InsightFlow`，分支 `main`。先用只读命令核对工作树干净、B3 提交 `668dadd45fa9c8c372754c5185f49518500a5ab6` 是当前 HEAD 的祖先，B1/B2/5A 提交链仍在。若起点不符，先报告。
- 固定 `upstream-v2.1.0-rc0` 的 commit 为 `609bfde0ced76ff0a58c02ff5c741df768f44502`，tree 为 `2473c22e163a3879490848a7995eb2b7be7f6f50`；不得改 tag/tree。`.reviews/` 始终忽略、不提交。
- 保留 Phase 5A 的 KEEP 能力、安全边界和历史迁移；不为追求文件数删除额外能力或测试。B1→B5 是依赖链，整链回滚必须逆序。
- Windows PowerShell 5.1；按交接备忘设置 `UV_DEFAULT_INDEX=https://pypi.org/simple`、`PYTHONPATH=.`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。常规 uv 测试用 `uv run --locked`；只有 B4 可通过正规锁定命令更新依赖和 lock，禁止手工改 lock 或无锁运行。不要用 `git checkout --`、`reset --hard` 处理未知改动。
- 不派子代理。提交前逐文件核对实际 diff，不以脚本或代理的“已完成”代替 `git diff`、测试结果和提交内容。

## P0：先闭合 B3 遗留，再开始 B4

### P0-1 恢复 KEEP 主链的真实集成覆盖

`backend/tests/test_web_fetch_error_shell_meta.py` 目前主要覆盖归一化函数，原 `TestRenderedByRealProducer` 经 Browserless 删除后缺失。按交接备忘 §4 的接缝，改用仍保留的 Jina `web_fetch` 生产者，穿过真实 `readability`、`ToolProgressMiddleware`、`ToolErrorHandlingMiddleware` 和 `tool_result_meta`。先写/恢复会失败的测试，实测 Jina 渲染输出后定断言，再用最小改动使测试通过；不得照搬 Browserless 独有的目标状态头语义，也不得伪造生产者输出使测试虚绿。保留错误页、合法页、无关工具负控与网关暂态错误等有效覆盖；不能迁移的两条状态头用例应明确记录能力已删除的原因。

### P0-2 provisioner 裁决（已批准的本轮口径）

**保留** AIO 沙箱的可选外部 provisioner 客户端 `remote_backend.py` 和 operator 配置接入；本轮不额外删除远程客户端。理由：它仍处于 KEEP 的 AIO 模块内，仓库内 provisioner 服务已删除，但仅为缩减这一小段客户端而扩张 B4/B5 范围不合算。文档和配置必须明确它只对用户自行部署、兼容既有协议的外部服务可用；不得宣称仓库自带服务或端到端兼容已经验证。

`test_aio_sandbox_provider.py` 当前不只是 `len(x)==len(set(x))`：还断言了五个预期 mount path 的集合。它保留了**客户端 payload 形状检查**，但已无法验证被删服务端的 `_validated_extra_mounts`。在该测试附近补一条中文说明，准确描述这种覆盖降级；保留现有路径集合与去重断言，不要将其删成仅有去重测试，也不要编造新的服务端兼容证明。把此限制写进最终报告。

### P0-3 提交与完整离线基线

P0-1/P0-2 形成一个**独立修复提交**（建议 `fix: restore retained web fetch integration coverage`），不要 `git commit --amend` 改写已交接的 B3 SHA。这个修复提交是对旧“一批一个实现提交”纪律的显式例外，目的在于保持 B3 审查锚点可追溯；提交范围仅限直接受影响的测试和确有必要的文档/进度记录，不顺手扩大生产改动。

先跑两个相关测试文件与对应 lint；然后按交接备忘 §4 P0-3 的命令跑完整离线后端套件一次。将失败的**具体测试 ID** 与 `.reviews/phase-05-b2-residual-failures.md` 比较，不能只比较“39 个”总数，也不能把任何新失败笼统归为 Windows 环境。新增失败要定位并修复、重新验证；未完成该门禁时不得开始 B4。不要运行 `-m live` 或无意触发真实外部 API。

## B4：Skill 平台与依赖收缩

严格按 manifest 的 B4 条目、既有实施计划 Task 4 与 verification matrix 执行。保留 `skills/skillscan/**`、`security_scanner*` 及 KEEP 的五个运行时 public skills；混合测试保留 KEEP 断言。B3 移交的已删 provider 依赖/extras 也在本批清理。更新 Python/前端锁文件前后检查坐标变化，避免无关依赖漂移；使用锁文件校验和计划要求的前后端门禁。每个实际删除目标先解析绝对路径并确认位于仓库范围，禁止未经验证的递归 glob。完成后独立提交，提交信息固定为 `refactor: remove unused skills and dependencies`；工作树 clean，重跑相位证明脚本。任何门禁失败停止，不带病进入 B5。

## B5：孤儿清理、累计验证与对账

严格按 manifest 的 B5 条目、计划 Task 5/6 与交接备忘的跨批 deviation 清单执行，包括向导残留 `channel_connections`、前端死键/死路由分支、已删除模块引用和文档收敛。`make doctor` 与 `make setup` 是用户可见面，必须验证不会继续输出/生成已删能力。保持 DDG+Jina、Local+AIO、普通 task、MCP tasks、Analytics、安全门禁、迁移和 ORM KEEP 主链。

完成计划规定的后端、前端、Playwright、构建、Compose/真实数据库累计门禁；不能运行的项目写明“未运行”、原因与影响，绝不写成通过。按 `phase-05-count.py` 与 manifest 的预测口径做规模对账，明确 Phase 0 数字目标在 KEEP 契约下不可达，给出不可删成本分解；不得为凑数继续删 KEEP。独立提交 `refactor: converge insightflow capability surface`，停在 GPT review，不启动 5C/6。

## 汇报格式与停止条件

每完成 P0、B4、B5 一个可验收单元，就提供一段短的、可直接转给 GPT 的中文报告：commit/full SHA 与 parent、删除/修改文件数、命令/exit code/测试计数、manifest 偏差、锁文件/固定 tag/tree/工作树状态、未验证事项和下一步。报告引用 `.reviews/` 中的完整证据即可，不在对话里粘贴几万行日志。

遇到新增测试失败、KEEP 契约冲突、清单外大范围删除、必要的产品决策、锁文件无关漂移或不可恢复的环境障碍，立即停在干净且可复核的边界，说明事实和建议，不自行扩大权限。B5 完成后只提交 Task 6 最终报告，等待 GPT 验收。
