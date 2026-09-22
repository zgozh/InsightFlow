# Phase 5B 实施提示词：执行已批准的五批能力删除

Phase 5A 提交 `5af2a68` 的审计清单通过 GPT 复验，作为**第一轮安全删除清单**执行。

必须完整读取：

1. `docs/architecture/phase-05-capability-contraction.md`
2. `docs/removal/phase-05-deletion-manifest.yaml`
3. `docs/removal/phase-05-dependency-impact.md`
4. `docs/removal/phase-05-verification-matrix.md`
5. `docs/superpowers/plans/2026-09-22-phase-05b-capability-removal.md`
6. `docs/decisions/0002-phase-05-size-budget-reconciliation.md`

以及根/Backend/Frontend/实际修改目录下的全部 `AGENTS.md`。本提示词只是入口，manifest、影响报告和
施工计划才是执行主体。

## 裁决

- 一次任务连续执行 B1→B5，不在批次之间询问 GPT。
- 每批必须独立提交、独立门禁、提交后 clean；任一批失败即停止，不能继续。
- 五批存在依赖，安全回滚顺序为 B5→B1。修正 Phase 5A 文档里过强的“任意批次可单独 revert”表述。
- DDG + Jina、Local + AIO、OpenAI-compatible + DeepSeek、DeerMem + Noop、普通 task、MCP tasks 与
  Analytics/Harness KEEP 契约按清单保留。
- 2290 只是第一轮预测，不是最终认可体量；不要为了追 850–1050 擅自删除额外测试或 KEEP 能力。
- B5 后停在 GPT review，Phase 5C 和 Phase 6 不启动。

## 删除安全

- 所有删除目标来自 manifest。Windows 上先解析并验证绝对路径位于当前 repo，使用同一 PowerShell/Git
  上下文执行；禁止未校验的递归 glob、跨 shell 拼接、workspace 根递归删除。
- 遇到 manifest 漂移、额外 importer、动态入口或 KEEP 冲突，优先在当前批允许的 modify 文件中解除；
  需要新架构或扩大到下一轮候选时停止报告。
- 不删除历史 migration/ORM model，不降低 Auth/thread/artifact/SQL/Analytics/SkillScan 安全边界。
- 测试只能因被测模块删除而删；混合测试保留 KEEP 用例。

## 环境与提交

- uv 使用 `--locked`；只有 B4 可按计划更新依赖和 lock，禁止手工编辑 lock。
- 不使用 Phase 4 的 Playwright junction 作为新的仓库改动；可以复用本机环境并在报告注明。
- 提交 message 严格使用计划中的五条；不 squash。
- `.reviews` 不提交，固定 tag/tree 不变。

## 最终回报

严格按计划 Task 6 一次性报告，不只写“通过”。尤其必须包含：

- 每批 commit/full SHA、parent、文件/LOC/依赖变化；
- 每个门禁的真实命令、exit code、测试计数；
- manifest 预测 vs 实际；
- lock 坐标变化、最终容器/路由/provider/skill 清单；
- SSRF 事实口径、RAG/image 能力损失、归属保留；
- 工作树、tag/tree 和 Phase 5/6 状态。

