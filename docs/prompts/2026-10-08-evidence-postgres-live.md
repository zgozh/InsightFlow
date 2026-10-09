# PostgreSQL 耐久证据适配真实验证

实施 gpt-6-luna/max。只读适用 AGENTS、SQL evidence repository/codec/0001至0004 analytics migration、已存在 evidence tests；不读取整仓或真实记录。

## 范围与所有权

这是 AS12 的有限前置证据，不是完整 Gateway/调度/未完成run恢复验收。只拥有新建 `.reviews/evidence-postgres-live-20261008/` 和 `docs/acceptance/2026-10-08-evidence-postgres-live.md`，不改生产源码或现有测试，不操作29384/29385及已有容器、数据库、卷、账号。另一worker正在新增agent/roles.py及其测试，输出独立。

仅使用本机已有 PostgreSQL 镜像，禁止拉取/构建。若没有合适镜像或主机审批拒绝，输出准确阻塞，不绕过。可创建唯一命名的隔离 PostgreSQL fixture project/container 与唯一专有 volume；如需要host连接，端口从29386起先确认空闲，必须显式127.0.0.1，禁止默认0.0.0.0。新容器启动属于用户授权的完整验收范围；仍尊重主机实际权限拒绝。密码随机生成，仅进程内传入子进程/容器Env，不打印、不作为命令行参数、不得落盘明文。输出只容器ID、镜像、loopback端口、专属卷与状态，不打印inspect Env。不要移除既有任何容器/卷；本fixture也保留供后续AS12复用，并把安全重连方法写入报告（凭据DPAPI可保留）。

## V3 真实检查

使用现有生产 SQLAnalysisEvidenceRepository 与真实 PostgreSQL async sessions，不用fake engine。运行现有 analytics Alembic 增量链至0004，记录revision，不在真实应用数据库上迁移。

用唯一合成owner/thread/run和少量合成数字快照验证：

1. 写入、精确scope读回，另一owner/thread/run不可读取。
2. 同内容幂等，冲突不可覆盖，missing batch不返回部分结果。
3. PostgreSQL advisory lock 下两个独立session并发争夺run第20个记录位置，合计不越过20份，失败不得留下超额行。仅本fixture可直接创建seed；复用成功DTO构造，不写真实SQL到evidence。
4. 关闭连接池并重开，仍读取相同snapshot及digest。
5. 仅重启本新fixture PostgreSQL，等待健康后用新engine再次读取相同合成scope；记录数据volume保持、snapshotdigest一致。不得重启原栈或角色worker使用的服务。

脚本断言即执行证据，不新增永久复制实现测试。一次完整验证后，回读报告与机器状态JSON即可，不重复后端全套、不调用模型。uv只 --no-config --default-index https://pypi.org/simple --locked，uv.lock不得变化。

确认生产缺陷时先报告准确复现与受影响文件，不跨所有权修代码。最终给实际命令、退出码、revision、权限/并发/重开/重启结果、保留fixture状态及未覆盖的AS12 Gateway/checkpoint/unfinished-run边界。不得把本切片写成AS12完成。
