# Gateway 构建：锁文件索引漂移最小修复

用户完整发布任务继续；Gateway镜像 `uv sync --locked --extra redis` 因lock需更新失败，构建已停止。主会话读取diff确认现有未提交 backend/uv.lock 有大批 registry/下载URL从PyPI变为清华镜像；当前Dockerfile显式默认UV_INDEX_URL为PyPI。pyproject与此轮新增代码未加依赖。你是 `gpt-6-luna` / max，只负责这个构建阻塞，不派Agent、不部署、不升级依赖。

只拥有 `backend/uv.lock` 与 `docs/acceptance/2026-10-08-lock-index-build-fix.md`。其他worker正在只build Frontend（Dockerfile只使用frontend来源），禁止改frontend/Dockerfile/pyproject/Gateway源/真实env。不要改用户全局uv配置或系统环境。

## 最小修复与验证 V2

1. 用tomllib解析当前锁与 `git show HEAD:backend/uv.lock`（通过subprocess参数数组读取，禁止git checkout/reset）。严格核对全部包name/version、dependency graph/markers、manifest/constraints、本地workspace sources、sdist/wheel哈希/大小/上传metadata，保留有语义的本地改动。仅将已确认的PyPI↔清华registry及下载URL前缀归一后比较整个结构。stdout只统计坐标/哈希/metadata变化数量，禁止泄露潜在带凭据URL。
2. 若且仅若归一后完全一致，恢复HEAD的canonical PyPI锁bytes（不覆盖任何有意义包变化），记录这次修复仅索引来源。若不一致，报告具体包名/字段类别与最小候选，不盲目覆盖/重新resolve/升级。
3. 在backend用当前uv版本支持的明确PyPI index选项、--no-config（避免用户global镜像介入）、`uv run --locked --extra redis`执行一次小的import检查（sqlglot精确30.18.0、sqlalchemy、redis即可），不运行整套pytest。使用task局部CLI/env override，不改持久env；锁必须不被命令改写。执行前后SHA256一致，diff --check通过。若所有registry字段恢复HEAD，可明确锁的最终git diff为空。
4. 如果现有venv环境需下载但PyPI不可达，先报告网络问题，不能降级--frozen、删--locked或更改mirror重新锁。无需uv lock --upgrade/安装新库，也不为源URL还原机械重跑旧123/192/59等应用测试。

交付归一对比真实结果、精确执行命令/退出码、最终锁SHA/坐标不变证明，立即冻结给主会话。Gateway镜像重build由原builder收到主会话明确冻结后执行，不能自己同时build。

## 主会话裁决：补齐镜像缺失的制品元数据并恢复canonical锁

主会话已独立读回核对报告：213包坐标不变、哈希不变；除210 registry/2120 artifact URL外，只有 defusedxml/jsonpatch/olefile 各sdist和首wheel共6条记录缺HEAD的size/upload-time（12字段），其他完整结构相同。缺失的制品大小/上传时间属于镜像元数据，不是用户新增依赖或版本修改，本机镜像漂移已实际阻塞发布。

现在授权继续最小修复，无须向用户再次确认：仅在内存归一后的当前结构，为已列明6条且artifact hash与HEAD相同的记录补HEAD中那12个字段，再与HEAD完整结构比较。如果完全相同，将原始当前锁先保存在 `.reviews/lock-index-build-fix-20261008/` 忽略目录，然后写回HEAD canonical bytes。严禁补其他字段/更改版本或哈希/重新resolve。

执行此前已记录的同一明确PyPI/no-config/--locked --extra redis import检查（锁已改变，这次重试有明确原因），要求锁SHA在命令前后仍一致；成功后补记录真实结果、最终git diff为空，并立即冻结。若又有不同结构或网络失败，报告实际原因，不循环重试或放宽locked。
