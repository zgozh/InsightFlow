# 耐久查询证据 PostgreSQL 真实验证

本验收为 AS12 的有限前置证据，只验证现有 `SqlAnalysisEvidenceRepository` 在真实 PostgreSQL 上的耐久、隔离与容量边界。它不代表 Gateway、checkpoint 或 unfinished-run 恢复验收完成，也不代表 AS12 完成。

## 环境与隔离

- 使用本机已有镜像 `postgres:16`，镜像 ID 为 `sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6`；没有拉取或构建镜像。
- 独立 Compose 项目：`evidence-pg-live-20261008-c0efb9fd03`。
- 容器 ID：`5fdcfedc8678252bd0d368cf047dd4243b3ee7d4f1288d0d5099fa68bbed3ec4`；容器状态：`running`。
- 主机只绑定 `127.0.0.1:29386`；项目专属卷为 `evidence-pg-live-20261008-c0efb9fd03-data`，专属网络为 `evidence-pg-live-20261008-c0efb9fd03-net`。
- fixture 只写入唯一合成 principal/thread/run 和合成数字快照。没有访问既有 29384/29385 项目、真实业务库或真实记录；没有调用模型。
- 随机密码仅在验证进程和容器环境中使用；本机保留 Windows DPAPI CurrentUser 加密凭据，不含明文密码的命令行参数、日志或报告。凭据文件为 `.reviews/evidence-postgres-live-20261008/postgres-password.dpapi`。

## 验证与结果

使用生产 Analytics Alembic bootstrap 将全新 fixture 数据库从 `0001_analytics_control_plane` 迁移至 `0004_metric_grants`。版本表为 `analytics_alembic_version`；验收结束时 revision 为 `0004_metric_grants`。

`.reviews/evidence-postgres-live-20261008/verify.py` 直接导入生产 `SqlAnalysisEvidenceRepository`、真实 async PostgreSQL sessions 和现有成功 DTO 构造器。执行断言结果如下：

| 检查 | 结果 |
| --- | --- |
| owner/thread/run 精确 scope；其他 owner、thread、run 均不可读 | 通过 |
| 相同记录重复写入幂等 | 通过 |
| 同 identity 冲突拒绝覆盖原行 | 通过；fixture 内仅修改 artifact path 来构造冲突 |
| 混合存在/缺失 evidence ID 的批读取整体拒绝，不返回部分结果 | 通过 |
| 两个独立 `NullPool` engine/session 在 PostgreSQL advisory lock 下争夺 run 第 20 个位置 | 通过；保留 20 行，1 次成功、1 次以 `capacity_exceeded` 拒绝，失败项没有落库 |
| dispose 后以新 engine 重开并读取相同快照 | 通过；snapshot 为 34 字节，result digest 为 `06fe37e857e7efb27709fbf13c640848e908c8da67dfb82af8c842cfb68479c9` |
| 仅重启本 fixture PostgreSQL 容器后等待 `pg_isready`，再由新 engine 读取 | 通过；同一 volume 中记录、revision 和 digest 保持一致 |

机器断言明细与 fixture 状态见 [.reviews/evidence-postgres-live-20261008/state.json](../../.reviews/evidence-postgres-live-20261008/state.json)。compose 配置、重连脚本和加密凭据也保留在同一隔离输出目录中，供后续 AS12 复用。

## 实际命令

先用后端已有虚拟环境做脚本语法读取：

```powershell
backend/.venv/Scripts/python.exe -c "import ast, pathlib; ast.parse(pathlib.Path('.reviews/evidence-postgres-live-20261008/verify.py').read_text(encoding='utf-8')); print('syntax ok')"
```

退出码：`0`。

真实 PostgreSQL 断言运行：

```powershell
backend/.venv/Scripts/python.exe .reviews/evidence-postgres-live-20261008/verify.py
```

最终完整验证退出码：`0`。首次启动脚本在容器创建后因 `docker compose ps` 子命令没有继承 Compose 所需环境变量而退出码为 `1`；未删除该新 fixture。修正子进程环境传递后，通过同一 DPAPI 凭据恢复进程内密码并复用同一容器、网络和 volume，最终完整验证通过。期间没有变更生产源码、现有测试、依赖锁或既有项目。

本切片没有运行 pytest 或后端全套；真实 PostgreSQL 脚本内的断言是本次 V3 验收。Gateway/checkpoint、unfinished-run 恢复及 AS12 其他验收面仍未覆盖。

## 安全重连

在生成 DPAPI 凭据的同一 Windows 用户下，从仓库根目录 dot-source 重连脚本：

```powershell
. .\.reviews\evidence-postgres-live-20261008\reconnect.ps1
```

脚本只在当前 PowerShell 进程中解密凭据，必要时启动这个 fixture 容器，等待 PostgreSQL 就绪，并将连接 URL 放入当前进程环境变量 `ANALYTICS_EVIDENCE_TEST_URL`。连接地址是 `127.0.0.1:29386`，数据库和用户均为 `evidence_fixture`。不要打印该环境变量；DPAPI 文件只能由当前 Windows 用户解密。
