# PostgreSQL 隔离 fixture TLS 与运行准备闭合

实施gpt-6-luna/max，接续 final-postgres-runtime 准备。当前22:52已过此前模型额度提示20:59；若额度仍不可用，准确报告，不替代模型。

确切阻塞已确认：DatasourceSecret DTO仅tls_mode disable/verify_full与ca_pem；disable仅loopback/localhost。Docker gateway用postgres DNS访问当前29386 PG（ssl off）会被策略拒绝。**不得放宽生产TLS策略或伪装host**。参考 deployment-and-ops/SKILL.md 的配置可回退、健康检查、密钥不输出要求；用户已授权PG完整验收，无需重复许可。

所有权仅 `.reviews/final-postgres-runtime-20261008/`、新独立TLS准备/验收记录，以及本任务创建的PG fixture服务的TLS配置。另两个writer正在阶段backend与Frontend，绝不读/改其未冻结源码。29384/29385/已停MySQL不操作。

Docker Engine恢复范围：当前named pipe不存在。先只读核对Docker Desktop进程与本机已安装程序路径。若Desktop未运行，可一次Start-Process以WindowStyle Hidden启动既有Docker Desktop，这是继续已授权部署验收的环境恢复；不杀进程、不reset/reinstall/WLS迁移、不换socket通道、不运行原项目docker start。若程序已经运行但engine离线，或启动被主机拒绝，则准确报告需要用户手动恢复，不再尝试其他启动手段。启动后以docker version/info安全结果有界等待（单次≤60秒，最多两轮，期间更新），成功才续TLS。不得将“Desktop已启动”当作“Engine已就绪”。

允许为我们新建的 `evidence-pg-live-20261008-c0efb9fd03` 配置TLS：先核验精确container/project/volume和无其他writer，保存原PG配置/健康/所有合成库安全摘要；不修改原evidence_fixture的表/数据，不删库/卷，不重建数据。只读确认既有工具可生成证书，优先容器已有openssl或已有Python cryptography，禁止安装新全局依赖/拉镜像。

生成本fixture专用证书，SAN必须包含Docker实际连接DNS postgres（与实际container name可选）及测试127.0.0.1；使用当前时钟合理有效期。私钥只保存在本fixture专有volume内，postgres可读且权限0600，不输出key、不写命令参数或可分享报告；public CA/cert可在ignored输出安全保留，用现有DTO ca_pem引用。不要搭泛化PKI系统或新增业务服务。

可用postgresql.auto.conf/服务参数等现有机制打开ssl，在明确保存旧配置和可回退步骤后**仅对这个新fixture服务**reload/restart，保留同container/volume/data。健康与TLS探针失败须恢复本fixture原配置并如实报告，不碰其他服务，不绕过主机权限拒绝。原loopback plaintext探针可继续使用其既有合法配置，非loopback business验证必须verify_full且证书名称匹配。

验证至少：SHOW ssl on；使用本机合法verify_full连接与对应CA，pg_stat_ssl.ssl true；只读business账号SELECT仍成功且写权限仍拒绝；独立application DB owner仍可连接；原evidence_fixture已保存合成snapshot数量/digest及revision无变化。container网络路径的最终Gate连接只在统一构建后实测，本切片不要启动Gateway/Frontend/Nginx或真实模型。

随后闭合原runtime准备稿：env/DPAPI引用、正确containerDNS、两个独立DB/角色、immutable image参数、安全compose预检与具体最终probe。已创建app DB事实保留，不重复创建/旧oracle。最小语法/安全配置检查与本TLS真实探针，禁止全套。准确列执行/准备/未验矩阵，冻结记录后交主会话，不把它当AS03/AS12完成。
