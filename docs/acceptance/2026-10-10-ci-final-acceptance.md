# 2026-10-10 CI 与本机部署验收快照

本页记录提交 `b40ea6b497b6559eb0731cb6f370f53085fbd33d` 在 2026-10-10 的验收结果。以下链接对应这个历史提交当时的 GitHub Actions 运行，不表示当前分支或之后提交的状态。

该提交的六个工作流均完成并成功：

- [E2E Tests](https://github.com/zgozh/InsightFlow/actions/runs/38035027163)
- [Unit Tests](https://github.com/zgozh/InsightFlow/actions/runs/38035027186)
- [Backend Blocking IO](https://github.com/zgozh/InsightFlow/actions/runs/38035027159)
- [Frontend Unit Tests](https://github.com/zgozh/InsightFlow/actions/runs/38035027169)
- [Replay E2E](https://github.com/zgozh/InsightFlow/actions/runs/38035027166)
- [Lint Check](https://github.com/zgozh/InsightFlow/actions/runs/38035027164)

## 本机部署检查

验收目标为本机 `insightflow-acceptance-local` 部署，Nginx 入口绑定 `127.0.0.1:29384`。该端口是验收环境配置，不是默认部署入口；默认 Compose 入口仍为 `http://localhost:2026`。

Gateway 镜像与构建记录匹配，容器处于 running/healthy，且没有直接发布宿主机端口。检查确认入口绑定、Gateway 运行参数和挂载符合预期；应用数据库为 SQLite，按实际挂载解析的数据库可完成只读查询。四个运行时源码文件的容器内哈希与构建记录一致。

HTTP 探针中，`/`、`/health` 和 `/health/ready` 返回 200，匿名 `/api/auth/me` 返回 401。合成隐私检查确认新事件与历史事件投影会移除敏感查询 diff、保留普通报告 diff，并识别新增的敏感查询产物路径。

本机部署验收脚本 `gateway-rollout/final-acceptance.ps1` 返回 exit 0。原先的 Apply 命令实际返回 exit 1，原因是旧摘要等价性检查无法验证：冻结记录没有旧 Gateway 的完整配置，无法精确比较所有历史字段。后续验收按当前 Compose 契约逐字段核对运行配置和挂载，并完成数据库、隐私投影及 HTTP 检查；这项通过记录保留了旧 Apply 失败事实，没有把它改写为成功。

本页依据的本机原始记录保存在被 Git 忽略的 `.reviews/ci-20261010/final-handoff.md` 与 `.reviews/ci-20261010/gateway-rollout/final-acceptance.json`。上文已列出公开 CI 链接及部署检查结果，因此阅读本页不依赖这些本机文件。
