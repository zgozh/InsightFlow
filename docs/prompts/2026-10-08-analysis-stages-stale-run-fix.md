# 分析阶段同线程旧 run 回调隔离

gpt-6-luna/max。只改 frontend/src/core/analytics/use-analysis-stages.ts、必要的core/threads/hooks.ts（确有必要才改）、对应use-analysis-stages DOM测试与既有前端阶段验收记录，不改backend/合同/其他文件。

主会话独立审查发现：onCustomEvent/onRunSettled只验证thread相同，随后无条件setStreamMetadata(metadata)。同thread的新run开始后，旧run的迟到custom/finish可把当前run重新指回旧ID。现有scope声明要求新run不能串入其他run，需保护此实际可复现状态转换。

先用现有hook测试构造 old run metadata → new run metadata → old custom/finish，观察当前run回退，写一项持久回归；然后最小修复。区分可信新stream开始与迟到旧回调，已被新run替代的scope不能复活；不要只检查thread或仅仅payload==回调meta。状态/ref在thread切换清理，live/backfill异步仍有原cleanup保护；避免通用session框架和无限增长历史。

V1/V2局部hook状态修补，跑直接DOM节点或该小文件、受影响ESLint/Prettier，若实际改sharedhook签名则typecheck，否则保留既有通过证据。uv/pnpm不改锁，不构建/真实模型/容器。准确记录失败复现与最终结果，未部署不写真实AS09通过。
