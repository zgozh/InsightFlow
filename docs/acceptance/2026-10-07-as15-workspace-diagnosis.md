# 2026-10-07 AS-01/AS-15 认证与默认栈补证

## 结论

AS-01 认证门禁与 AS-15 默认四服务启动的场景条件均通过。跨 owner 404 body 会回显请求方已经提交的 A thread UUID；与随机不存在资源的错误形状相同，没有暴露资源标题、artifact path 或正文。A thread 未提取到 title marker，标题内容不可用/未测试；datasource list 为 0 条，未把不存在的值描述为已验证数据。SSE 完成后内容 replay 归 AS-09，不阻塞本次认证门禁。

基础容器、owner 与合成 run 证据见[默认栈记录](2026-10-07-as01-as15-default-stack.md)。

## 真实认证门禁

复用隔离四服务栈 127.0.0.1:29385，不重启、不注册、不 seed。DPAPI 凭据只在 PowerShell 当前用户进程解密，通过进程级环境变量传入 probe，运行后清除；账号、fixture 标识和响应正文没有打印或保存。

| 请求主体 | 检查 | HTTP / 内容结果 |
| --- | --- | --- |
| A、B | 各自读取 thread；A 读取自有 artifact 与 admin datasource list；B 读取 user datasource list | 均为 200；artifact 正文与合成 fixture 匹配。A admin datasource list 为 0 条；B list 只验证了状态，未读取或保存其记录数/正文 |
| 匿名 | A thread、A artifact、admin datasource、user datasource | 均为 401；响应正文不含 6 个现有合成 ID/path/body 标记 |
| B | 读取 A thread、A artifact、admin datasource | 404、404、403；响应不含 A 的 run ID、artifact path/body 或 datasource 标记 |
| B 与随机不存在资源对照 | 随机不存在 thread；A thread 下随机不存在 artifact | 均为 404。thread 错误 body 仅归一化各自请求 UUID 后一致；artifact 错误 body 完全一致，不形成存在性 oracle |

B 的 thread/artifact 错误 body 会回显请求中已给出的 A thread UUID，probe 单独记录了这一点。它不含 run marker、artifact path 或正文；A thread 没有可提取的 title marker，标题内容不可用/未测试；A admin datasource list 为 0 条，故没有行级标记。匿名接口对 6 个存在的合成 fixture 标记逐一比较均无命中。所有响应正文只在 probe 进程内比较。

## 浏览器与启动证据

匿名分析路由跳转 /login；A 登录和 /me 为 200。A 自有分析线程的 metadata、history、messages、models 请求均为 200，输入框最终可见且启用；analysis/new 输入框也可见且启用。B 经分析路由读取 A thread 返回 404 并显示终态拒绝。pageerror、API requestfailed、runs/stream POST 均为 0。没有配置或调用模型；models endpoint 的 200 不表示模型 key 已配置。

隔离 Compose 栈由默认四服务 base 与仅覆盖命名、镜像、绑定和隔离挂载的 overlay 构成；此前已通过 Compose --wait 启动，nginx/frontend/gateway/redis 均 healthy，宿主只发布 loopback 29385，Gateway/Redis 无宿主映射，SQLite 位于隔离挂载。readiness 不是把 overlay 误报为 root make up 原样启动。

## 定点检查

- 在 backend 执行 test_gateway_startup.py 中 readiness probe、deploy success 和 deploy failure 三个直接 case。设置 PYTHONUTF8=1 后为 3 passed、exit 0；首轮仅因 Windows 默认 GBK 解码 subprocess UTF-8 输出失败。
- 用 DPAPI 环境变量运行 ignored auth_gate_probe.py，exit 0；只输出身份角色、HTTP 状态、布尔比较、标记计数，不写 response body。
- ignored browser_probe.cjs 的 node --check 与真实浏览器采样均 exit 0。
- 未运行全套测试，未改产品代码/配置/容器，没有调用模型、commit 或 push。
