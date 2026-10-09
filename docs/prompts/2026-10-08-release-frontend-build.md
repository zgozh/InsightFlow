# 冻结前端一次生产镜像构建

gpt-6-luna/max。只拥有新 `.reviews/release-stage-build-20261008/`中frontend专用输出及 `docs/acceptance/2026-10-08-release-frontend-build.md`。Frontend阶段/旧run修补已冻结：12项原验证、修补5项、typecheck/ESLint/Prettier证据保留。另worker仅修Backend terminal stream，不读/改其源码，不启动/重建任何容器或数据库。

按frontend/Dockerfile现有production构建方式，用独立新tag `insightflow-release-frontend:stage-20261008`（若已存在先报告，不覆盖未知镜像）。先只读Dockerfile/.dockerignore确认context敏感 .env/config/.reviews/app-home 不会COPY进镜像；只记录规则，不读打印真实配置。必要build args沿用现有compose默认，不改源码/锁/全局npm或registry。不单独先跑pnpm build，再重复docker build。

实际构建一次frontend，Docker Engine当前已恢复且只允许此镜像build；不得buildGateway（还在修补），不得up/start/recreate29384/29385/29388。输出适量或保存本fixturebuild log，不打印整个base64/敏感env。

构建成功记录immutable image ID、tag与实际命令/退出码、source文件摘要（Frontend关键冻结文件即可），不将tag名字当Image ID。这是V3发布构建，失败分类查准确根因，依赖下载临时问题/代码问题报告并有针对性修复请求，不跨所有权改生产；不重复先前unit/typecheck。完成冻结供后续统一PG runtime预检/部署传显式imageID。
