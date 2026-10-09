# 最终暂存与锁一致性检查

gpt-6-luna/max。用户已授权验收完成后commit/push，但此slice **仅暂存，不commit/push**，Principal最后审查staged后再授权机械提交。

所有权 backend/uv.lock（仅恢复精确canonical）、docs/acceptance/2026-10-09-final-delivery.md最后检查事实、`.reviews/final-postgres-runtime-20261008/final-review/`自己的safe stage摘要、git index（stage）。其它production/tests/docs冻结，不运行业务tests/build/Docker/model。

Principal最后read发现全uv.lock registry被本机Tuna配置污染。已从验收image读取 `.reviews/final-postgres-runtime-20261008/final-review/canonical-uv.lock`，SHA256准确 `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`（整个会话原始受保护canonical）。当前污染SHA f0a475…与registry2375行差异不得提交。先用tomllib比较两锁的package版本/依赖/所有artifactsha保持同一，仅registry/source下载域变化（其他变化必须Root报告，不盲覆盖）。核对pyproject内容与image构建时依赖面未变，此slice直接Copy canonical bytes恢复并readSHA，不能重新uv lock/sync，不复跑套件。

所有后续命令避免本机uv rewrite：已装venv python/ruff直接用；如必要uv必须--no-config/--locked/--no-sync和官方defaultindex。Stage期间不uv run。不改变用户全局uv配置；提交hook如需设置UV_NO_CONFIG/UV_DEFAULT_INDEX仅子进程当前作用域并还原，不把环境写入项目。

1. 更新final-delivery：sharedproxy1passed/178数学角色报告Reviewer、preflightversion一致/秘密扫描无高置信凭证、锁原始SHA恢复，Windows旧残差已分层定点passing，原29384升级postchecksallpassed。仍不写已commit/push/CI绿。
2. 当前main、暂存空、工作树全部二开目标变更范围前序授权。只读status候选，不加入个人config/env/.reviews/.deer-flow/cache/DB/keys/临时备份；对于全部goal代码/tests/docs/资源及语言文件删除，可 git add -A（ignored protections必须先确认），但任何明显范围外个人文件先列路径不盲stage。
3. 暂存后 `git diff --cached --check`、文件列表数量/addeddeletedstat、canonicallocksha、版本两个source2.1.0-rc0一致、无secret/privatefile候选。安全扫描仅staged文本新增或已有全file，禁打印命中值，只path/type/line，可按测试fakefixture合理分类，不因为parserregex falsepositive改tests。
4. 给Root stagedsummary/exactgitcommands/exit及异常，立即freeze。不要提交/推送/改history或tag，不重跑API。Linux远程CI尚未执行，预期push后CI可能启动，不能宣称它已有结果。
