# 提交前最后收口检查

gpt-6-luna/max。用户已授权全部验收后commit/push，当前AS11最后运行尚在验收，**此切片不commit/push、不stage、不Docker变更、不运行测试**。独立所有权 `.reviews/final-postgres-runtime-20261008/final-review/` 自己的precommit输出，以及README/README_en/Install/docs/current-capabilities和final-release-matrix仅最终事实/引用更新，不改其他worker正在写的验收文件、PROGRESS/INTERRUPTION/production。

最新known evidence：目录UI完整passed；realPGproducer/collector scope与原artifacthashpassed；取消隔离HTTP FakeAgent测试passed；未完成run通过真实PG独立DB+生产worker/lifespan跨进程恢复 error/orphan_recovered，精确cleanup；HTTPtimeout5s+audit/active0passed。AS11旧runs Reviewerreject，mapping补丁96tests通过已rootsource审查、当前newGateway11dd部署后正在唯一new自动once验收，未有结果不能写passed。

任务：

1. 只读git工作树stat/变更路径，对二开目标待提交文件生成可审查scope摘要（新增Analytics/roles/tests/UI/docs/Phase5移除等）。所有目标前序会话授权变更可纳入，不因历史dirty丢掉；明显个人config/cache/log/DB/private runtime/.reviews不得进入。禁止reset/clean或删用户文件。
2. 只读检查拟提交文本是否意外包括真实secrets/环境配置/DSN/证书privatekey/用户数据。禁打印任何命中值，仅文件路径/行号/类型/计数；测试fakefixture允许依据上下文明确分类，不为falsepositive机械批量改tests。已有gitignored config/.env/.deer-flow/.reviews保持，若真实秘密被跟踪先report，不stage。
3. 明确两版本源相等、根RELEASING/适用CI gates与有效证据，roles39/Reviewerreports96/前端类型与构建/局部tests已有通过不重跑。纯V0 docs链接检查/`git diff --check`可做一次，任何真实静态问题给精确路径，别整仓format。
4. 文档最终knownfacts/矩阵更新：AS06HTTPtimeout证据、AS08分层取消和实际失败处理、AS12真实PG复用/unfinished恢复均已proof，不强求付费live取消替代隔离真实HTTP（无模型不影响取消机制）。旧13个Phase5全suite失败保留有据，不因当前改动自动宣布消失，确认是否适用发布门禁。当前用户主打个人企业级但不能伪造全部底层原创，法律保留。AS11pending保持，最后结果Principal再更新。

输出安全precommit review/拟commit范围/确定未满足适用门禁，quick冻结。不要凭“未测试任意全部配置”增加门禁，比例工程复用有效证据。最终commit/push由Principal总体验收后另派机械操作。
