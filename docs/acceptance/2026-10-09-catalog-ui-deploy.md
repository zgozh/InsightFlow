# 目录分析操作部署验收记录

## 构建产物

- 候选 Frontend 镜像为 sha256:365f55389e29117a5d81cb6afa8a87ef22e411a94c41c995b25a3cc9a5b3c066。
- 首次构建脚本以退出码 1 结束：Windows PowerShell 5 将 Docker stderr 当作 NativeCommandError，导致脚本未读取并记录 Docker 子进程退出码；frontend-build.log 为空，因此不声称构建子进程退出码为 0。
- 候选镜像已存在。既有镜像核验脚本退出码为 0，确认 ChatPage 源文件哈希与工作区一致，并确认编译产物清单及 pnpm start 入口存在。按任务要求未重跑构建。
- build_frontend.ps1 已为后续调用增加局部 ErrorActionPreference Continue 和紧邻读取 LASTEXITCODE 的处理；本次候选镜像不是通过该修正后的脚本重新构建。

## Frontend 部署

- 既有 Frontend-only 部署命令完成容器更新，Compose up 子进程退出码为 0。当前 Frontend 容器 401ebf1ada020791fbde625f92ae443c4d74f9fd4274ed17bdbecbcfe2c0114e 正在运行候选镜像。
- 部署脚本最终退出码为 1，失败码为 post_update_invariant_failed。安全只读复核确认 Frontend 已重建并运行目标镜像；Gateway 容器 a9bd2d34c47f4f17b4db39240b63b83ea46a44eda223a98a5c57f969efdaa055、Nginx 容器 7558d230dfca40c08b8beddd1b421f9960eebbb116ca5620d3e56670e4081112、Redis 容器 1c2c66daa6767818c66cbdf14f122ce430f212ddf62da682e8d2f12203d83fee 均未变化，状态仍为 running；Nginx 仍发布到 127.0.0.1:29388。
- 原 Frontend 镜像 sha256:e1f8f0b85dc9b06274918db46a4c6f64c8a578327bdb74264809f6e607b105ee 不在本机镜像库中，旧镜像保留检查失败；没有拉取、重建或清理镜像。只读复核确认本地 stage-20261008 镜像 sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c 仍可用，但本次没有用它回滚。
- 部署脚本在失败分支没有写出 frontend-deploy.json；当前 Frontend 的 Better Auth secret 与 Gateway internal token 均存在。由于最终完整部署检查没有成功落盘，本记录不把部署脚本整体标记为通过。

## 浏览器检查

- 按提示只修改既有探针的 visibleTextarea()：等待首个 textarea:visible locator 最多 10 秒，等待超时仍映射为稳定失败码。没有修改产品、构建或部署服务。
- 调整后仅执行一次既有 run_catalog_ui_browser_probe.ps1，退出码为 0。数据源与指标目录操作均校验到正确资源 prompt，预填草稿可编辑；窄屏目录操作可达；普通聊天与已有成功分析页没有套用 sentinel prompt；run_post_count=0、model_post_count=0、runtime_console_or_page_errors=0。
- 脱敏证据文件 .reviews/final-postgres-runtime-20261008/frontend-release/browser-check.json：

  {"status":"passed","login":"synthetic_b_dpapi_ui_login_http_200","datasource_prefill_editable":{"route":"datasource","viewport_width":1280,"action_reachable":true,"correct_resource_prefill":true,"draft_editable":true},"metric_prefill_editable":{"route":"metric","viewport_width":1280,"action_reachable":true,"correct_resource_prefill":true,"draft_editable":true},"narrow_datasource_action_reachable":true,"normal_chat_prompt_not_applied":true,"existing_successful_analysis_prompt_not_applied":true,"run_post_count":0,"model_post_count":0,"runtime_console_or_page_errors":0}

- DPAPI 凭据未写入报告或证据文件。
