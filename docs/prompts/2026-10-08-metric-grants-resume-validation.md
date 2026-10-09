# 指标授权后端恢复与冻结

用户已撤销暂停，要求继续完整发布任务。实施模型 `gpt-6-luna` / max。工作区 `D:\develop\workspace\InsightFlow`，主会话已恢复读取生产 diff，旧任务 Agent 已不存在。

先读适用根/backend/analytics AGENTS 与 `docs/prompts/2026-10-08-metric-grants-backend.md` 冻结契约。不是重新开发：表/0004/repository/management/API/新回归均已落盘。原定点5文件126项中123通过，3失败；暂停前修补可能已经完成。当前只完成残余验证和必要修补，尽快冻结交主会话审查。禁止扩展背景阅读、重写现有实现、部署、前端修改、真实账号/数据修改或派其他 Agent。

## 需要闭合

1. 读取实际测试断言，确认 API `test_metric_grants_require_admin_and_are_visible_only_after_explicit_grant` 区分 owner自己的ACTIVE可见与普通账号授权前不可见。迁移 `test_bootstrap_creates_exactly_the_analytics_tables_from_an_empty_database` 应断言0004；旧0001→0002报告迁移基线排除0003 evidence和0004 grants。rg查真实旧迁移用例名称，不猜名字。
2. 运行这3个此前失败的用例；如果仅修测试断言与format，不重复已通过123项。如发现生产逻辑变化，仅再跑直接受影响的grant/目录/管理用例。
3. 对 management.py、catalogs.py、test_analytics_persistence_migrations.py 做必要 Ruff format，后做所有本切片受影响文件 Ruff check / format --check 和 git diff --check。使用 `uv run --locked`，native Windows设置UTF-8以免GBK污染证据。
4. 主会话审查发现 catalogs.py 的grant还增加了非SQLite/PG fallback分支，而应用只支持SQLite/PG。移除该无需求compat分支，未知dialect稳定拒绝（沿用PersistenceDataError稳定reason、不得异常带driver文本），保留SQLite/PG幂等ON CONFLICT实现。直接覆盖未知dialect拒绝或用已有受支持dialect构造校验；不要新增第三种database适配。
5. 保留既有版本前进/save/retire语义、owner-only管理保护、ACTIVE+grant目录、歧义key默认拒绝。不要改此前耐久 evidence、MEDIUM预算、品牌内容。

## 所有权与交付

可改本切片原有后端metric文件、直接相关tests及 `docs/acceptance/2026-10-08-metric-grants-backend.md`，不得改总PROGRESS/INTERRUPTION、前端或Gateway。

验收文档补上实际执行命令和结果；原123通过仍有效，修复后3通过必须明确是否真的执行。不得将多个测试命令相加为不实独立用例数。说明尚未部署、前端未接线、完整15场景仍未验收。

完成后返回精确modified/new文件、关键diff和检查结果，冻结文件。遇到环境问题先报告真实错误，不循环重跑未改变命令。

## 主会话独立审查后的最后补正

生产读取、owner保护、固定grant路径与0004表结构已独立读回，未发现放宽数据源权限的问题。API新增用例授予后的断言仍只读取admin自己的目录，缺少普通账号实际GET的正向证明：在grant后、revoke前增加ordinary GET /metrics断言返回已授予的revenue（可同时保持owner断言）。只跑这一个API用例即可。

同时把 SqlMetricRepository 类docstring 从旧“exact-owner scoped，不引入共享目录”更新为当前真实语义“管理读写按创建者隔离，普通目录仅允许已启用且获授权的指标”。将本切片验收文档最后新增加的英文自有说明改为中文，补真实单用例检查结果。此微切片仅改 catalogs.py注释、test_analytics_api.py该用例、本切片验收文档，不动其他后端production/前端/AGENTS。其他Agent将并行接前端及Gateway bridge，文件所有权互斥。
