# 显式预填分析草稿隔离

gpt-6-luna/max。实测source action预填通过，但再点metric action时共享new草稿覆盖显式初始值。已有InputBox按draftKey只hydration一次，普通编辑保护成熟，应复用而不是重写draft管理。

独立所有权 frontend/src/components/workspace/chats/chat-page.tsx、直接相关前端tests、docs/acceptance/2026-10-09-prefilled-analysis-draft-fix.md。不改InputBox通用hydration/后端/文档worker拥有文件，不部署或发模型。

最小实现：仅当 analysisMode && isNewThread 且 analysisPrefill 非空时，draftThreadId 使用当前生成的 threadId；普通聊天与无预填新分析仍用原new键，历史thread用原threadId。不要清空用户所有草稿，不改session存储底座；复用已存在的threadId与hydratedDraftKey保护手动编辑。确认目录重新进入新分析的threadId生命周期会产生新ID，若同组件复用须解决不同prompt共享相同ID的实际问题，先读useThreadChat机制，不凭猜测。

回归必须覆盖真实连续source→编辑→metric→不同新草稿并正确初始值→再次编辑后rerender不覆盖；普通聊天和无prompt分析旧草稿不受影响。测试尽量复用现有InputBox/helper fixture，不只测三元表达式镜像。定点相关测试、typecheck/受影响文件lint一次；不全suite。

交实际补丁/最小checks/是否有残余生命周期限制，冻结供Principal最终审查。之后单次前端build/deploy+原两clickprobe验收，不在本slice自行部署，不新run/model。
