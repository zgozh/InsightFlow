# 发布后 UI 与身份修复部署证据

日期：2026-10-09。部署目标为原栈 `insightflow-acceptance-local`，浏览器入口仍为 `http://127.0.0.1:29384/`。

## 构建与部署

- `python scripts/pnpm.py build`：exit 0，复用已安装依赖；`BUILD_ID=rD3w0sXWIMihhrwJHx4vq`。
- Gateway 从 `insightflow-feedback-gateway:server-computation-20261009` 派生为 `insightflow-feedback-gateway:post-release-identity-20261009`，只复制 `prompt.py`：exit 0。
- Frontend 从 `insightflow-release-frontend:catalog-ui-20261009` 派生为 `insightflow-release-frontend:post-release-identity-20261009`，复制生产 `.next` 并排除非运行时 `dev`、`cache`：exit 0。
- 对 `insightflow-acceptance-local` 执行 Compose `up -d --no-deps --no-build --pull never gateway frontend`：exit 0；只重建 Gateway 和 Frontend。新容器 ID 前缀分别为 `99593831903a`、`3fa55cbd8bf9`。
- `backend/uv.lock` SHA256：`46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`，与 canonical 值一致。

## 部署后证据

- Gateway `/health` 与 `/health/ready` 均为 HTTP 200；容器健康状态 `healthy`。原入口 `/` 为 HTTP 200。
- 运行中 Gateway 的默认 `apply_prompt_template()` 结果包含 `InsightFlow`，不含旧品牌或旧仓库链接；运行镜像内 `prompt.py` SHA256 与源码一致：`ada2c5f3cbe8f1ce349a6592f5262bf2ee3f766cfa8ef64afef51ceee09209b2`。
- Frontend 容器中的 `BUILD_ID` 与构建产物相同；522 个生产静态文件逐文件哈希一致，静态树 SHA256：`86be702e1040c03f82597e464ca58699eacb06fbe95af8134f575b023635e666`。导航实现源码树 SHA256：`5c816b855ef00ec53588e1468bd67bd990fc9c992193cfc5e7cfb0d56ac99af1`。
- Nginx、分析演示 PostgreSQL、Redis 容器 ID 均与部署前相同；入口仍绑定 `127.0.0.1:29384`。`app-home`、`redis-data`、`analytics-demo-data` 卷仍存在，Gateway 挂载配置未变。
- 导航路由矩阵单测 7/7 通过。Live 浏览器访问 `/workspace/chats` 被重定向到 `/login`，没有可复用登录态；因此未执行登录后的浏览器矩阵，也未创建或重置管理员。未发起模型请求。

