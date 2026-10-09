# 清理本项目已废弃验收容器并继续新验收环境

gpt-6-luna/max。用户要求清理不用的容器。主会话独立审查：全机30个容器均exited；原29384演示5容器和PGfixture必须保留；29385已完成验收，仅自身4容器关联网络as01-as15-1bf6932f3abd_deer-flow，无其他容器依赖，MySQL已改可选并停止。以下5容器允许仅docker rm（不-v、不force、不compose down、不prune），删除前重新核对完整ID/项目/状态/端口与数据承载。

- MySQL b89e394f76224c2af0ba88224354b6eee1eb63ed63bd542b21a540d21f20d3b1
- AS01/15 Gateway 3a8639de4f895ccc9fad155822a7b26f338f61325ae7d23fe4c1b5017cb25406
- AS01/15 Frontend 92a623ba3f7d33f2fda9b87d5b52d2f2bf6b5e3f1993468da64008d412e1921c
- AS01/15 Nginx b6ef444d369b6c80546382333c8cb63573c8733c413a0fe635d30050ab2e6cb7
- AS01/15 Redis 28e00c4a76d41c170de92f2a33a97228a3b16cfb524945ef91ba3f29672b6fe4

保留数据卷、网络、镜像、manifest、host bind app-home、DPAPI和验收证据；原29384真实账号/报告容器不动。只清这5个，不泛化清理。确认数据承载在这些保留资源；AS01/15 Frontend没有volume，但仅合成验收账号/状态，该容器不再承担用户演示服务。

用户已通过异步问题明确回答旧2027“已不用，删除容器并保留数据卷”。因此另外允许删除project=insightflow-analytics-demo的5个已停容器：Gateway短ID ba1f52e3b0c8、Frontend 74cc5ba815e0、Nginx 9490a74b1fe2、PostgreSQL cd740a7da66b、Redis 62c14e9fe3cd。按inventory取得完整ID，重新校验项目/姓名/exited与各卷挂载；不用前缀批量删、不-v、不force。原29384 project=insightflow-acceptance-local不能混淆。总计10个授权废弃容器，原先“不泛化清理”限制仍适用。

其他分类事实：docker项目13容器working_dir为D:/develop/workspace/deer-flow/docker，doc-qa的PG是D:/简历/doc-qa，属于其他项目，完全不动。用户对这两组没有删除授权。

所有权：startup-probes/下retirement专属安全记录、现有gateway-reuse验收记录相应追加；不改另worker runtime-probes/、生产代码或镜像。执行安全native wrapper已有stderr修正，只输出ids/count/status等。精确删除成功后 inspect 验证容器缺失、原数据volume/network和29384/PGfixture IDs存在，并记录数量变化。

然后继续已授权的启动里程碑，不再次build：新Gateway eed9b69ce4174479952040f3e27be213bc54d5d91d6d7faf3de40060451517e6与Frontend fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c。PGfixture现已exited，需要仅恢复你拥有的evidence-pg-live-20261008-c0efb9fd03-postgres-1，完整ID5fdcfedc8678252bd0d368cf047dd4243b3ee7d4f1288d0d5099fa68bbed3ec4，先核对volume/network/固定image，docker start该fixture后等health并verify_full探针。不得自动start原29384或其他项目。

主会话另发现实际默认入口缺陷，需要先做一次缓存修正构建，以上“不再次build”仅禁止重做完整apt/uv安装。当前派生Dockerfile末尾WORKDIR=/app/backend，继承的CMD仍是cd backend，导致默认docker run解析到不存在的/app/backend/backend。runtime.compose的working_dir=/app虽覆盖此问题，但交付镜像默认入口也必须正确。在ignored派生Dockerfile末尾加WORKDIR /app，其他层不改；只在现有pg-20261009 tag仍等于上述eed9 ID时允许更新自己创建的tag。缓存构建应只改变镜像配置，原uv安装层缓存复用，不再取包。成功后核对Config.WorkingDir=/app、Cmd不变、记录新immutableID并用新ID启动，旧eed9不作为最终镜像。无须重跑已通过source/import验证，依赖层没有变化。

使用现有launcher默认预检后 -Apply只启动新iflow-final-pg-20261008/29388，按既有新镜像提示的健康/PG迁移/checkpointer/business连接门禁执行。不发模型、不seed或改grants。遇主机拒绝报告准确动作与理由，不绕过；遇真正runtime源码问题交回主会话。不得因为容器删后曾存在而重建29385/MySQL。
