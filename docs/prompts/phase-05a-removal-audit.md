# Phase 5A 实施提示词：能力删除审计与精确清单

Phase 4（主提交 `ae89805` + Fix 01 `65b499d7`）已通过 GPT 复验。偏差 1 的 EOF 规范化处理接受。

现在只执行 Phase 5A 审计，不执行任何删除。完整要求在：

1. `docs/architecture/phase-05-capability-contraction.md`
2. `docs/superpowers/plans/2026-09-22-phase-05a-removal-audit.md`

必须从头读取两份文件，以及根/Backend/Frontend/实际扫描目录下的全部适用 `AGENTS.md`。本提示词是
入口，架构文档和施工计划才是大头。

## 强制边界

- HEAD 必须为 `65b499d76273d303e51ebb4b26b91b0e4c2e72f1`。
- 只改 Phase 5A 四份交付文档、`docs/PROGRESS.md` 和本提示词；`.reviews` 保持忽略。
- 生产、测试、config、依赖、lock、Docker、CI、skills、assets 删除/修改数必须为 0。
- 不安装依赖、不跑 Docker/全套测试、不提前启动 Phase 5B。
- 不凭目录名判定删除；必须检查 import、router/lifespan、config 字符串路径、registry、dynamic import、
  filesystem route、migration、tests、scripts、CI 和 docs。
- 不给 GPT 多个开放选择。根据证据给出唯一推荐批次；真正无法证明时把该项标为 BLOCKED/KEEP，说明
  缺什么证据，但继续审计其他域。

## 特别裁决

- `deer.svg` 必须进入第一个前端删除批次：先移除认证页可见引用，再证明零引用后删除资产。
- 历史 migration 默认 KEEP。
- 普通 subagent、Skill runtime、MCP core、Scheduler、Memory DeerMem/Noop、Local+AIO sandbox、
  OpenAI-compatible+DeepSeek、Analytics 安全主链必须 KEEP。
- 只保留一个 Web Search/Fetch 实现，按真实默认配置、依赖和工具主链给出推荐，不因“以后可能用”
  保留 provider zoo。
- 安全测试不能为达到文件预算被删除。

## 提交前自检

使用临时/`.reviews` 脚本验证 manifest：YAML 可解析、所有路径存在、分类互斥、目录 keep exceptions
明确、批次预测可加和、十个候选域全部覆盖。脚本不提交。

最终只创建一个提交：`docs: audit phase 5 capability removal`。

## 回报格式

一次性报告：

1. commit/parent 和精确提交文件（证明生产/测试/lock 等零变化）；
2. 当前精确规模与统计口径；
3. 最终 KEEP 白名单；
4. 3–5 个推荐删除批次及依赖顺序；
5. 每域入口、动态引用、配置、依赖、测试和 replacement 摘要；
6. 每批删除/修改/测试数量与累计预测，最终是否进入目标/硬上限；
7. manifest 自洽检查命令、exit code、关键结果；
8. `git diff --check`、tag/tree/lock/工作树；
9. BLOCKED 项与保守处理；没有则写 `None`；
10. 明确 Phase 5B 未启动，等待 GPT 对清单一次性复验。

