# ADR 0004：LocalSandbox 子进程环境改为有限白名单

- 状态：Proposed，待 GPT 复验
- 日期：2026-09-25
- 决策人：Phase 6E1 实施与架构复核

## 背景

LocalSandbox 曾从 Gateway 的完整 `os.environ` 复制子进程环境，再按变量名关键词和少量精确名称排除凭据。该规则只能识别已知命名形式；Analytics 的 `env://<name>` 可引用任意有效变量名，因此 `BUSINESS_ACCESS` 一类不含敏感关键词的凭据仍会进入本地命令子进程。

## 决策

LocalSandbox 改为只继承 `sandbox/env_policy.py` 中显式列出的精确运行时变量白名单。白名单按平台大小写语义匹配，未知名称默认拒绝。凭据只可通过既有 request-scoped 授权流程显式注入；`is_blocked_env_name()` 保留为配置投影的凭据名称分类器，不参与子进程继承决策。

白名单包括命令查找与 Windows 启动所需的 `PATH`、`PATHEXT`、`COMSPEC`、`SYSTEMROOT`、`WINDIR`；用户和当前目录路径 `HOME`、`USERPROFILE`、`HOMEDRIVE`、`HOMEPATH`、`PWD`；临时目录 `TMP`、`TEMP`、`TMPDIR`；shell 与虚拟环境发现 `SHELL`、`VIRTUAL_ENV`；本地化变量 `LANG`、`LANGUAGE`、`LC_ALL`、`LC_COLLATE`、`LC_CTYPE`、`LC_MESSAGES`、`LC_MONETARY`、`LC_NUMERIC`、`LC_TIME`；终端变量 `TERM`、`COLORTERM`。Windows 不区分大小写，POSIX 区分大小写。

`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 均不继承，因为值可能携带凭据。`NO_PROXY` 也不继承：它会调整代理绕过路由，而且不是启动命令所需变量。没有加入 `*_URL`、`PYTHONPATH`、`PYTHONSTARTUP`、任意 `DEER_FLOW_*`、`ANALYTICS_*` 或其他通配模式。

AIO 容器仍只从运维配置的 `sandbox.environment` 构造环境。以 `$NAME` 引用 Gateway 变量是运维主动授权；本平台不能阻止运维主动映射 Analytics 数据源凭据。

## 备选方案

| 方案 | 决定 | 原因 |
| --- | --- | --- |
| 继续用名称黑名单并追加 `ANALYTICS_*`、URL 或其他模式 | 否决 | `env://` 允许任意变量名，有限 denylist 无法证明未知值不含凭据；宽模式还会留下漏项或误删正常变量。 |
| 清空所有环境变量，只保留显式注入 | 否决 | 会丢失定位可执行文件、临时目录、Windows 进程启动和本地化终端所需的最小运行环境。 |
| 同时改变 AIO `sandbox.environment` 解析策略 | 不在本切片 | AIO 当前路径是运维显式配置映射；这属于不同的信任边界，需独立设计，不能把主动映射描述成平台已阻断。 |

## 后果

- 未列出的 Gateway 变量不再自动传给 LocalSandbox 命令。依赖任意继承变量的本地自定义脚本需改用已授权的 request-scoped 注入，或调整其运行方式。
- AIO 配置映射仍能有意把 Gateway 值传入容器；运维必须审查 `sandbox.environment`，尤其是 Analytics 数据源凭据。
- LocalSandbox 仍在 Gateway 主机执行 shell 命令，白名单不是文件系统、进程或网络隔离边界。
