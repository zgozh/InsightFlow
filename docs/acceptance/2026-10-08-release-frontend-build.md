# Frontend 生产镜像构建冻结记录

本记录冻结 2026-10-08 的 Frontend 独立生产镜像构建，供后续预检和部署显式传入 image ID。

## 构建结果

- 结果：成功，Docker build 退出码 `0`。
- Docker Engine：`29.1.2`。
- 镜像 tag：`insightflow-release-frontend:stage-20261008`。
- 不可变 image ID：`sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c`。
- 镜像大小：`528377370` bytes。
- 构建时间：`2026-10-08T23:38:02+08:00` 至 `2026-10-08T23:41:18+08:00`。
- 完整构建日志：[frontend-build.log](../../.reviews/release-stage-build-20261008/frontend-build.log)。
- 可供后续流程读取的 image ID：[frontend-image-id.txt](../../.reviews/release-stage-build-20261008/frontend-image-id.txt)。

tag 仅用于本地标识；后续流程应传入上面的完整 image ID。此构建不表示部署完成、运行时预检通过或 AS09 通过。

## 构建命令与上下文

在仓库根目录执行了唯一一次 Frontend Docker build：

```powershell
docker build --progress=plain --file frontend/Dockerfile --target prod --tag insightflow-release-frontend:stage-20261008 --build-arg PNPM_STORE_PATH=/root/.local/share/pnpm/store --build-arg NPM_REGISTRY= .reviews/release-stage-build-20261008/context
```

使用原 `frontend/Dockerfile` 的 `prod` target、根 `docker/docker-compose.yaml` 中 Frontend 服务的默认 build args，以及 `COPY frontend ./frontend` 所需的目录布局。构建上下文暂存于 `.reviews/release-stage-build-20261008/context`，只含 Frontend 目录和根 `.dockerignore`；未将 Backend 纳入上下文。构建期间 Dockerfile 内的 `pnpm install --frozen-lockfile` 与 `pnpm build` 正常完成；没有单独重跑 pnpm build、unit、typecheck、ESLint 或 Prettier 检查。

Frontend 目录没有独立 `.dockerignore`，实际使用根 `.dockerignore`。它排除 `**/.env`、`.env.*`、`config.yaml`、`extensions_config.json`、`.reviews/` 和 `**/.deer-flow/`。暂存步骤也显式排除了这些配置/运行时路径；构建上下文中没有 Backend、配置文件或运行时 home 内容。这里只记录排除规则，没有读取或输出配置内容。

## 源码快照摘要

- 仓库 HEAD：`a678d54b4b4b61ea74b05e37ebc342f5bb983cf8`。
- 构建前 Frontend 工作树状态：37 个已修改文件、2 个已删除文件、16 个未跟踪文件。变更涉及 analytics API / 阶段面板、landing 场景与图片、workspace/chat/settings/navigation、i18n、thread/sidecar，以及配套测试和资源。
- 本次构建没有写入仓库源码或锁文件。镜像构建使用上述 Frontend 暂存快照；root `.dockerignore` 仍排除 tests、scripts、docs 及非 README Markdown 文件。

关键暂存输入的 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `frontend/Dockerfile` | `763bdbe44a3da28c22a2eb821335a256defea1c9b239a8fb60a7eeae7119aab8` |
| `frontend/package.json` | `4012d08b84229dcc6f4274bd14bb41665412251e2d6ff7f48318858f2eb972c4` |
| `frontend/pnpm-lock.yaml` | `2ccd85dd6b3a5dd8f9e65eb5928b57d22da4f2ae085ff7d7a8a0759cc0f7f7cf` |
| `frontend/next.config.js` | `7dc2a4b7a2e0063ee8f003e26d3956c026d8ee63f8e0ab2c526bc302612c981d` |
| `frontend/src/app/layout.tsx` | `67e564e3feed483966113a9347e17465542b25d676eb45598131f289feb44b38` |
| `frontend/src/components/analytics/analysis-stage-panel.tsx` | `ea9c42330295f8314beb9577812985a10d7888d1981996281b1a6c41de8cc5d2` |
| `frontend/src/core/analytics/analysis-stages.ts` | `a12ca7fd91243cf02f96feb81c33c7b5ea6c8c69cc5312269c59b38c7e229ec2` |
| `frontend/src/core/analytics/stage-events-api.ts` | `e5b5f751ad43728e577ad0ab9d115a495e076a2fa81235fdf9d3b27c942168f0` |
| `frontend/src/core/analytics/schemas.ts` | `c869b3e56b618591e02e2e891a502fcdd55bef184234b01c731f8c3b6b4fcc5b` |

## 边界

本次只构建并冻结 Frontend 镜像，没有启动、重建或重新配置任何应用容器或数据库，没有构建 Gateway，也没有运行 Gateway/PG runtime 预检或部署。已有 Frontend 验证证据保持原样；本任务没有重复执行这些检查。
