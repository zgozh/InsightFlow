# 最终 PostgreSQL 运行验收准备

gpt-6-luna/max。只准备运行环境与具体probe，不构建、不启动新Gateway/Frontend/Nginx、不调用模型、不读另两个worker正在修改的生产实现。以现有稳定AGENTS/config/compose/auth接口及已冻合同为依据；接口不清楚准确报告。

所有权：新增 `.reviews/final-postgres-runtime-20261008/` 与 `docs/acceptance/2026-10-08-final-postgres-runtime-preparation.md`。不得改生产/合同/已有fixtures。当前用户最终范围是PG必验MySQL可选，禁止追加MySQL验收或启动已停MySQL。

目标：角色+阶段前后端冻结后统一构建，并在独立PG应用库、PG业务源与合成普通账号上实际验证，不操作29384真实账号。默认四服务已验，不更改默认compose。可以规划复用既有隔离29385账号/SQLite来补默认启动，但核心PG应用恢复准备应使用唯一新project/空闲loopback入口29388等，不动原项目/数据。现有PG fixture 29386可复用：business DB analytics_fixture_20261008只读账号已建；原evidence_fixture绝不改动。仅本fixture新增独立application DB/拥有DDL的独立app账号可供可选应用PG验收，不能用business只读账号写app表。

凭据仅从现有DPAPI/用户已配置本地文件在进程内解析；不得打印Env/配置内容/密码/token、CLI带密码或落盘新明文凭据。新fixture密码DPAPI保存，配置用env引用。容器内PG连接需外部fixture网络/DNS5432，不能把host 127.0.0.1:29386误用为容器内部地址。Compose预检只输出安全服务/镜像/端口/网络/mount字段。生产真实model配置可引用既有已配置source/mount，不能杜撰供应商key或偷偷调用模型。

准备脚本须以已构建immutable image ID为显式参数，pull never/no build；当前阶段不执行部署。新应用Home/卷必须独立，Nginx只显式127.0.0.1入口，Redis仍required。PG应用与业务分开数据库/角色；依据已有支持配置确认Harness history/checkpoint/run events与Analytics迁移路径，缺实际支持不能用图纸宣称。

准备最终单次主正向run：合成admin A负责登记数据源/schema/policy/指标并授予普通B；B发起明确经营分析请求，真实角色链→artifact/evidence→数字oracle→报告list/preview/download→live custom stage与永久GET events一致→刷新回填。所有schema/样本均来自既有受控fixture，必要currency字段若原表没有先报告，不擅改旧oracle。prepare probe可先写好但不执行未构建的新功能。

记录其他待收尾：真实慢查询timeout、取消/失败（可用离线HTTP模型fixture避免付费重复）、定时分析复用、PG应用restart/history/checkpoint/evidence/artifact与unfinished-run truthful状态。对checkpoint续跑来源run的server provenance缺口，仅标当前待验，不自行修改生产实现。

V0/V3准备检查仅脚本语法、DPAPI/数据库连接安全字段、compose静态安全摘要（不启动），不跑旧oracle、不全套。确认新application DB创建权限/可用性可在本PG fixture独立范围操作，主机拒绝就停止操作不绕过。最终准确给已准备/已执行/未执行矩阵与具体命令，不能把准备稿当验收通过。
