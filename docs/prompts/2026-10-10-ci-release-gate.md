# CI 修复提交前最后机械门禁

实施者 gpt-6-luna/max，D:/develop/workspace/InsightFlow。所有前实施者已冻结，无并行作者。主会话已独立审查30个实际变更及新增测试；接受run.end安全类型保真和query-result敏感diff设计。

## 仅剩事项

1. 前worker仅检查最后6个Python文件，最初17失败涉及的Python仍需覆盖。从 git diff --name-only 取本轮所有已修改.py文件（限定backend），使用现有backend/.venv或根.venv的Ruff对这些文件check与format --check。只修报告的未使用import/机械格式，不能整仓format/重构。不重跑已通过14项/2win skip、workspace6、lifecycle1、前端3或build。
2. 后端修复记录分片编号有误，只纠正编号/日志映射：job114115994285是shard1(2fail)，114115994295是shard2(6fail)，114115994212是shard3(4fail)，114115994196是shard4(5fail)。当前正文对应病例都正确，别改写事实。记录最后完整affectedRuff结果。
3. backend/AGENTS.md 的Analytics/事件说明适当位置加一句：服务端query-result*.json只参与workspace变更元信息，正文不生成diff；旧事件读取在副本中过滤，报告与普通文件diff仍保留。不要改CLAUDE，不重复README大段。
4. git status列6个未跟踪测试临时目录，不得提交：backend/.pytest-ci-repair-lifecycle-20261010、...20261010b、.pytest-ci-repair-lifecycle-model-20261010、.pytest-ci-repair-targeted-20261010、.pytest-ci-repair-tmp、.pytest-ci-workspace-evidence-20261010。如存在，把它们保留到已ignored .reviews/ci-20261010/temp-fixtures（精确名字），不得删除用户数据/其他缓存。Windows Move-Item -LiteralPath前检查每个源与目标绝对路径仍在本仓库，不能跨shell/字符串拼命令，不覆盖已有目标。无需为清理修改.gitignore。
5. git diff --check和uv.lock SHA25646f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912核对。freeze返回实际新增diff与所有检查结果；暂不commit/push。主会话复审后再授权正常提交和新Actions验证。

当前permissions danger-full-access/approval never，不传sandbox_permissions。禁止Docker操作/模型请求/历史证据重跑。正常hooks最终必跑，不通过workflow跳过测试，CI待新提交真实结果。

## 提交授权

主会话已独立读回最后机械修正/指南说明、完整工作区名单与lock hash，全部接受。现在正常 stage 本轮38个预期文件（31个已跟踪变更与7个验收/prompt新增文件），正常 commit 并 push origin main，不跳过hooks、不force/tag/PR。作用域内UV_NO_CONFIG=true、UV_DEFAULT_INDEX=https://pypi.org/simple、UV_NO_SYNC=true，执行后恢复，保护lock。若hooks有实质代码改动返回审查，不擅自补大修；机械format可记录。提交前拒绝任何额外未知文件，不stage .reviews/.env/数据/tmp。message使用 fix: 修复 CI 契约与查询证据事件隐私。返回真实commit/push exit与local/remote SHA、clean状态。CI由主会话读取新Actions，不本机重跑suite/build。
