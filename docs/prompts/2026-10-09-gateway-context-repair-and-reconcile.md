# 修复遗漏源码并受控续启新 PostgreSQL 验收栈

gpt-6-luna/max。前一切片已冻结：新项目4容器已创建，Redis/Frontend running、Gateway exited1、Nginx created；Gateway唯一异常deerflow.sandbox缺失。Canonical源模块存在且tracked，冻结context遗漏，并非依赖或业务源码问题。主会话审查认可此根因。目标是修正构建输入和新项目受控重建，继续真实启动门禁。

所有权仍为gateway-build-20261009/内新修复Dockerfile/context材料，final-postgres-runtime/的launcher与startup-probes安全记录，本切片验收文档。禁止碰runtime-probes、生产源码/正式Dockerfile/锁、原29384/其他项目、已清理的29385/2027/MySQL。无模型/seed/grants。

1. 将canonical `backend/packages/harness/deerflow/sandbox/` 源码原样补入冻结context对应路径，排除__pycache__/pyc/真实.env等运行数据；不能用全局basename sandbox排除代码模块，旧backend/sandbox是runtime排除项。对backend/app与backend/packages的生产.py做相对路径覆盖检查，排除缓存/运行目录而非合法代码包。若除sandbox之外还缺代码，列出实际路径并一并恢复对应源码；别只修第一个import后循环盲构建。记录 missing-before/after count，关键冻结源码hash保持不变。
2. 保留已锁定依赖，不重走apt/uv安装。以已经拥有全部依赖且WORKDIR=/app的现有703a15480954b4a52979fd1b2f35bfea39e1958bba4deb85728890e645958656镜像作本地基础（当前pg-20261009 tag，build前核对ID），新增ignored修复Dockerfile只COPY被遗漏的源码目录；若检查只缺sandbox，就只COPY该包。新tag `insightflow-release-gateway:pg-final-20261009`，先确认不存在，pull=false。继承正确入口/工作目录，禁止将缺失旧703作为最终发布版本。
3. 新镜像离线import deerflow.sandbox及PG extra、检查/app/WorkingDir/Cmd与恢复代码hash；输入文件无秘密。既有依赖与其它源码证明保留，不重跑应用suite/前端build。
4. 最初launcher拒绝任何已有项目，此时partial project正是你刚创建的4个容器。增加仅本固定project的显式 -ResumePartial 与 PreviousGatewayImageId 参数（允许旧703的Gateway，others必须匹配传入固定Frontend/Redis/Nginx IDs），保留默认拒绝已存在project行为。续启前严格核对exact service set=4、固定container names/project labels、原image IDs、已知卷/网络的project归属，拒绝未知/缺失/多余资源。网络/volume存在仅对验证过的本partial允许，不泛化绕过guard。
5. 同一次ResumePartial Apply会生成一致的内部auth/BetterAuth token，因此Gateway和Frontend需要一同受控recreate，不能只换Gateway留下Frontend旧token。此项目尚未有用户/模型run/报告，允许这次配置恢复；所有app-home/Redisvolume/PGdatabase不删除。Nginx可随正常依赖up启动，Redis无需强制重建。Compose范围固定新project，no-build/pull=never，传新final imageID；PGfixture已running/pg_isready+loopback verify_full通过，不重复重启。

V1+V3：修复输入覆盖与Pythonimport/PS AST，受控续启后实际四服务healthy/running、29388 health与首页200、唯一loopback发布、应用PG migrations/checkpointer表、Gateway内business verify_full实际连接与3row/SELECT-only。只输出安全boolean/count/revision/hash，禁止Env/DSN/密码/SQL结果/完整compose。预期非零native commands局部EAP=Continue保留exit，模板用无内引号的简单字段/JSON内存解析，避免已发现的Windows引号bug。无需新泛化框架或大矩阵。

若出现新真实启动故障，定位一个具体safe cause；配置/构建小缺陷在此已授权切片内窄修复，生产源缺陷必须交回Principal。不要把状态未变当成理由重复命令。实际迁移/容器/HTTP没通过不得宣称完成。尽快冻结实际diff、命令/checks、新immutable ID和启动结果供主会话审查。
