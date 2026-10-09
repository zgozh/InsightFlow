# 目录分析操作构建部署

gpt-6-luna/max。主会话已独立审查analysis-prefill.ts、目录链接与ChatPage新分析限定预填，接受26项测试/typecheck/static证据，不重跑。仅此改动需要生产构建/真实页面验收。

所有权 `.reviews/final-postgres-runtime-20261008/frontend-release/` 与 `docs/acceptance/2026-10-09-catalog-ui-deploy.md`。前端生产源码冻结；后端、安全probe、README、旧29384不动。与另一worker安全API探针无共享写文件，不要重启Gateway/PG/Redis。

复用之前fae029bd…构建的已有frontend Dockerfile/构建上下文流程与本地cache，标准生产build一次，固定当前frontend source/lock hash。不要重装主机依赖、不重跑tests。确认正式Dockerfile实际路径，不凭记忆猜路径。

构建后只更新29388项目frontend服务，保留现有BetterAuth/网关内部token和挂载，复用先前安全Gateway deploy的内存env/compose方法，不跑初次Apply，不换认证secret，不重建其它服务，旧image保留rollback。

使用既有合成B DPAPI登录浏览器，在数据源和指标目录各点击新增操作，确认到 `/workspace/analysis/new`、正确资源草稿可编辑、没有run POST/模型调用；普通聊天/已有成功analysis页面未被prompt覆盖。检查页面无runtime错误，桌面/移动窄宽布局操作可达即可，不做大截图矩阵。

短记录build exit/newimage/service IDs保持/浏览器checks；实际指令与安全证据后冻结。不得提交push，等最终所有验收完成。
