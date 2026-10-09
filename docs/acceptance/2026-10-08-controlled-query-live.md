# 双库受控查询真实验收前置

日期：2026-10-08<br>
范围：生产 composition、真实 PostgreSQL/MySQL adapter 与独立业务数据库 fixture。未调用模型；不覆盖 Gateway HTTP、Agent 角色、运行阶段事件或报告闭环。

## Fixture

- PostgreSQL 16：127.0.0.1:29386，业务库 analytics_fixture_20261008，只读角色 analytics_cq_20261008_reader。
- MySQL 8.4：127.0.0.1:29387，业务库 analytics_fixture_20261008，只读角色 analytics_cq_20261008_reader；实测 lower_case_table_names=0。
- 两库含同一张 monthly_metrics 合成表和 3 行固定小样本。只读角色可 SELECT，权限检查与回滚写入探针均确认 INSERT/UPDATE/DELETE 不可用。
- PostgreSQL 的业务库与角色在既有 evidence-pg-live-20261008-c0efb9fd03 容器内新建。原 evidence_fixture 数据库只用于读取服务器版本与角色创建权限；没有对原库表写入、更新或删除。
- MySQL 使用本机已有 mysql:8.4 镜像，Compose 使用 --pull never、无 build，项目/网络/volume 独立命名为 controlled-query-live-20261008；端口仅发布到 127.0.0.1。容器保持运行供后续角色验收复用。
- 数据库只读密码保存在 DPAPI 文件 .reviews/controlled-query-live-20261008/fixture-passwords.dpapi。脚本在进程内解密并通过环境变量传递，不把明文写入命令行、日志或文本配置。
- 任务独立的 SQLite Analytics 控制库和真实迁移位于 .reviews/controlled-query-live-20261008/analytics-control.sqlite3，内含本切片的 datasource、schema、policy 与审计记录。

## 实际证据

通过 build_analytics_services 装配真实 SqlDatasourceRepository、SqlSchemaSnapshotRepository、SqlAccessPolicyRepository、SqlExecutionPlanStore、SqlQueryAuditLog、PlanAnalyticsQuery 和 ExecuteAnalyticsQuery；没有替换为 fake catalog、estimate 或 executor。

PostgreSQL 与 MySQL 都通过相同 oracle 检查。直接 SQL oracle 使用只读凭据和独立连接，逐项比较列名、规范化值与类型；完整低风险结果和两种截断结果的返回前缀均匹配。LOW 与 MEDIUM 聚合 oracle 摘要相同；全部三个用例摘要都在两个引擎间一致：

    聚合结果 SHA-256：ac0af84b949b4c6a62216f63fb13ca9ffaf9948aa83f627fca42fe649baccf67
    字节截断 oracle SHA-256：728c219d91e5ebd27c48ad072cb7278115785b3187fa484a33e3a8926e5c1bcd

| 用例 | PostgreSQL | MySQL |
| --- | --- | --- |
| LOW 聚合 | plan/execute 成功，3 行，oracle 值/类型/列名全匹配 | plan/execute 成功，3 行，oracle 值/类型/列名全匹配 |
| MEDIUM 自连接聚合 | 计划限额 2000ms、2 行、200 bytes；返回 2 行并以 result_limit_reached 截断，值与 oracle 前缀匹配 | 同左，值与 oracle 前缀匹配 |
| MEDIUM 字节限额 | 返回 1 行、163 bytes；result_limit_reached，oracle 前缀匹配 | 返回 1 行、163 bytes；result_limit_reached，oracle 前缀匹配 |
| LOW 计划限额 | 4000ms、4 行、400 bytes | 4000ms、4 行、400 bytes |
| 重放同一 plan | 第二次执行返回 plan_unavailable | 第二次执行返回 plan_unavailable |
| PII / HIGH | authorization 阶段以 sensitive_column 拒绝；无 plan | authorization 阶段以 sensitive_column 拒绝；无 plan |
| 危险函数 / blocked | policy 阶段以 dangerous_function 拒绝；无 plan | policy 阶段以 dangerous_function 拒绝；无 plan |
| 未登记 principal | datasource_unavailable | datasource_unavailable |

HIGH 与 blocked 用例执行前后，持久化 plan 数均未增加。应用审计包含 16 条完整终态记录；审计列名符合批准的结构字段集合，未发现原始 SQL、凭证或样本行。所有 plan 已在 claim 后删除；datasource 仅保存 env:// secret reference。

LOW 与 MEDIUM 的服务端计划限额确实不同：statement timeout 为 4000/2000ms，行数为 4/2，字节数为 400/200。这里证明的是风险派生和执行限额截断；没有运行慢查询，因此不声称真实数据库 statement timeout 已触发。

## 复现与后续复用

一次完整前置运行命令及退出码：

    .\.reviews\controlled-query-live-20261008\run.ps1
    exit code: 0

Python 源码语法检查和 PowerShell runner/reconnect 脚本解析均通过。安全摘要与逐项布尔断言保存在 .reviews/controlled-query-live-20261008/run.log。完整 runner 为 .reviews/controlled-query-live-20261008/fixture_live.py。

语法检查分别以 Python compile（backend/.venv/Scripts/python.exe，exit code 0）和 PowerShell Parser.ParseFile（run.ps1、connect-fixture.ps1、disconnect-fixture.ps1，exit code 0）完成。DPAPI 解密、只读连接 JSON 的回环地址/端口/业务库断言，以及清理两个环境变量的复用检查也通过，exit code 0。

后续最终角色验收可在启动 Gateway 的同一个 PowerShell 进程中加载已有只读凭据，然后直接复用上述数据库和样本：

    . .\.reviews\controlled-query-live-20261008\connect-fixture.ps1
    # 从当前进程启动 Gateway，并运行角色验收
    . .\.reviews\controlled-query-live-20261008\disconnect-fixture.ps1

连接脚本只把 DPAPI 解密后的只读 credential JSON 放入当前进程环境；不会重建数据库。完成后用 disconnect 脚本清除环境变量。

## 尚未覆盖

- 真实 PostgreSQL/MySQL statement timeout 终止行为；本次没有执行慢查询或扩大数据量。
- Gateway HTTP、认证/授权路由、自然语言 Agent 工具调用、模型调用、阶段事件、evidence/report 持久化及浏览器流。
- 统一构建后的角色 run；由主会话在角色接线完成后复用此 fixture 做最终验收。
- 本切片未运行全仓测试或真实模型验收。过程没有操作 29384/29385，也没有改动原 evidence_fixture 业务数据。
