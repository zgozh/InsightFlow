# 查询证据 diff 隐私边界与 CI 最终切片

实施者 gpt-6-luna/max；已有worker全部冻结。主会话已独立核对真实生产路径。

## 确认根因

唯一剩余 lifecycle 用例已走通计划、执行和报告，私有哨兵泄漏仅在 workspace_changes 的 metadata.workspace_changes.files[1].diff。文件为 outputs/query-result-<run-id>-<digest>.json，是服务端durable evidence产物。recorder按普通文本捕捉diff，阶段/工具消息投影并不能覆盖它。这是生产隐私缺陷，禁止删除/放宽测试哨兵断言。

## 最小设计（复用已有机制）

- workspace_changes/scanner.py 已有 SENSITIVE_PATH_PATTERNS/is_sensitive_workspace_path/_snapshot_file：敏感路径不读取正文，并用现有 sensitive=True/diff_unavailable_reason="sensitive" 合同。把服务端 query-result-*.json 命名纳入该分类，保持元信息、owner artifact访问、报告diff和其他普通文件行为，不关闭整个workspace diff。不重命名/搬迁证据文件、改SQL权限或新增schema。
- 新扫描阻断未来持久diff；旧记录也需安全读取。复用路径分类实现简短的 workspace payload 安全投影：只对敏感文件清空diff、标记sensitive及已有reason（必要归零该文件line additions/deletions），不修改输入/存储原记录。由 workspace_changes/api.py 的 get_workspace_changes_response 与 runtime/serialization.py 的 project_analytics_event_rows（workspace_changes metadata/旧content payload）复用，避免历史事件API或独立workspace API继续外发旧diff。不要建新通用抽象或屏蔽正常报告变化。
- 中文说明安全原因；run.end preserving_types修复保留，不回滚其他已通过修改。

## 验证与输出

1. 为scanner与历史payload/API读取写有长期价值的定点回归：query-result哨兵不进入snapshot正文/diff，普通report.md diff保留，历史事件和独立workspace读取都遮蔽且不修改原记录。
2. 修完一整个切片后运行相关workspace/serialization定点用例及唯一lifecycle node，保留plan/execute/report/evidence/owner/跨线程/私有断言。测试模型nonstreaming与get_accessible已补，fixture数字73报告断言按已验证数值和引用，清理临时诊断。
3. 所有本轮改动Python文件Ruff lint/format；仅修真实报告，无全仓格式化，不再跑有效14pass/2win skip。无付费模型、Docker栈操作。
4. 更新/新增 docs/acceptance/2026-10-10-ci-backend-repair.md，保留原17失败对应根因以及新增隐私发现，列实际检查命令/结果/Windows skip/LinuxCI待验。简洁，不改历史验收结论。
5. freeze返回actualdiff与精确检查，主会话独立审查后正常commit/push并读新Actions；不得改workflow、skip失败或continue-on-error。

仅拥有backend/与后端验收文档，未改root/frontend文件保持。uv.lock字节不能变。sandbox失败需tool require_escalated具体申请，不绕过。
