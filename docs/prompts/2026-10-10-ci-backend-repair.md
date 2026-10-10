# 后端 CI 失败集中修复

实施者 gpt-6-luna/max，根目录 D:/develop/workspace/InsightFlow。读取根/后端/目标目录 AGENTS，使用 systematic-debugging 已由主会话读过：先确认根因，再定点修复，不机械扩大测试。

## 范围与证据

GitHub fa0213c Unit Tests run 38019134148 四分片17失败。实际日志失败段落已存 ignored .reviews/ci-20261010/job-114115994285.txt、job-114115994295.txt、job-114115994212.txt、job-114115994196.txt，末尾包含完整nodeid。只处理这些失败及必要的直接关联契约，不扫所有历史验收。

拥有 backend/ 中直接关联的测试与必要生产文件；若需修改根 CONTRIBUTING.md/.dockerignore/Makefile等，先根因报告及明确最小范围，不修改前端文件。可以写 docs/acceptance/2026-10-10-ci-backend-repair.md 安全证据。另一worker拥有前端与其格式，不能跨写。

先按精确17 nodeid复现（现有backend .venv，不uv自动同步，缓存写可用/tmp或-p no:cacheprovider），分类测试过时/真实产品回归/平台差异。缺少Skill目录不能通过skip/xfail/只删除参数来放绿，应保护现有保留公开Skill的真实导出安装行为，必要合成fixture保留不同特性。报告MIME若是系统guess_type差异，用符合明确artifact契约的跨平台断言，不为过时测试修改生产输出。分析runtime新绑定能力需真实或合适隔离fixture补齐，不绕过failclosed。finish()已持久化终态返回tuple并由worker bridge发送，测试须覆盖实际契约，不重新使用过期writer、不放弃live/durable一致性要求。其余失败也按日志源码确认根因，禁止弱化owner、安全或SQL边界。

## 验证与交付

V1/V2：成组修改后一次运行直接受影响测试文件及Ruff lint/format。只对真实新失败修复重测，不本机全套14k；新提交会自动触发Linux CI，最终V3以Actions真实结果验证。用现有venv工具，uv.lock canonical SHA25646f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912不可改。禁止改workflow跳过测试/continue-on-error/屏蔽gate，禁止付费模型与Docker栈修改。

完成冻结返回每个失败nodeid的根因、实际diff、精确检查命令/结果、生产代码是否变化及风险，暂不commit/push，主会话独立审查。权限限制按工具require_escalated申请，不绕过拒绝。

## 根目录范围授权

已确认直接失败根因，允许最小修改 CONTRIBUTING.md 补 live 测试命令与 opt-in 说明，以及 .dockerignore 精确放行公开 .env.example；真实 .env 与凭据仍必须排除。Makefile 现有三平台分支保留，只更新对应测试检查MSYS/原生Windows shim/POSIX分支。LOCAL_TRIAL 已迁移配置说明至 Install，旧文档断言按真实说明位置更新，不恢复重复历史说明。

配置层次说明迁移时遗漏，允许在 Install.md 最小补充真实模型、扩展、环境与凭据配置关系，并将 quickstart 测试迁到正确文档，保留有价值的配置说明契约，不机械固定整段措辞。
