"""沙箱命令子进程的环境变量策略。

LocalSandbox 只继承下方明确列出的运行时白名单。Gateway 凭据和其他运维变量不会自动进
入子进程；只有调用方通过 request-scoped ``injected`` 参数显式传递时才会加入。
``is_blocked_env_name`` 是配置投影使用的独立凭据名称分类器，不决定子进程继承范围。
"""

from __future__ import annotations

import fnmatch
import os

# 配置投影使用的凭据名称分类规则，按不区分大小写的方式匹配大写名称。
# 未命中规则只表示该字段名未被分类为凭据，不代表 LocalSandbox 会继承它；
# 子进程继承范围由下方独立的精确白名单控制。
_SECRET_NAME_PATTERNS: tuple[str, ...] = (
    "*KEY*",
    "*SECRET*",
    "*TOKEN*",
    # ``*PASS*`` 覆盖 ``PASSWORD``/``PASSWD`` 全称和 ``DB_PASS``、``SMTP_PASS``、
    # ``MYSQL_PASS`` 等缩写；``PGPASSFILE`` 也因此被分类为凭据字段。
    #
    # ``GIT_ASKPASS``、``SSH_ASKPASS``、``SUDO_ASKPASS`` 表示凭据助手程序而非秘密值，
    # 但助手可代表调用者提供凭据，因此配置投影也应将这些字段按凭据处理。
    #
    # 即使名称只是偶然包含 ``PASS``（如 ``COMPASS_*``、``BYPASS_*``）也会分类为凭据，
    # 以避免把可能的敏感配置投影给模型。``PWD``/``OLDPWD`` 不含该子串，不受此规则影响。
    "*PASS*",
    "*CREDENTIAL*",
    "*DSN*",  # data source name — almost always a connection string with a password
)

# 这些连接串或凭据字段名不含 KEY/SECRET/TOKEN/DSN，但值通常内嵌密码（如
# ``postgresql://user:pw@host/db``）。不屏蔽所有 ``*URL*``，以免把无害服务 URL
# 从配置投影中误删。技能若确实需要某项凭据，必须通过 ``required-secrets`` 声明，
# 再由调用者通过 ``context.secrets`` 提供，最后经显式注入传递。
#
# 同一原则也适用于客户端直接读取的凭据来源：``MYSQL_PWD`` 和 ``REDISCLI_AUTH``
# 是对应客户端支持的无参数凭据变量；``REDIS_AUTH`` 虽不是 Redis 客户端标准名，
# 仍按凭据分类，因为客户端库和部署模板常设置它。Postgres 的 ``PGSERVICEFILE``
# 指向可能含密码的 ``pg_service.conf``；其兄弟 ``PGPASSFILE`` 已被 ``*PASS*`` 覆盖。
# 这些名称必须精确列举：通配 ``*PWD*`` 会误伤 ``PWD``/``OLDPWD``，而 ``AUTH``/
# ``SERVICEFILE`` 没有可安全使用的共同标记。
_BLOCKED_EXACT_NAMES: frozenset[str] = frozenset(
    {
        "DATABASE_URL",
        "DATABASE_URI",
        "REDIS_URL",
        "MONGODB_URI",
        "MONGO_URL",
        "AMQP_URL",
        "RABBITMQ_URL",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
        "MYSQL_URL",
        "CLICKHOUSE_URL",
        "CONNECTION_STRING",
        "CONN_STR",
        "GH_PAT",
        "GITHUB_PAT",
        "MYSQL_PWD",
        "REDISCLI_AUTH",
        "REDIS_AUTH",
        "PGSERVICEFILE",
        # ``SSH_AUTH_SOCK`` 指向宿主 ssh-agent；持有该 socket 的进程可调用其中密钥签名，
        # 无需读取密钥文件。配置投影将其视为凭据指针；子进程是否继承则独立由白名单决定。
        # ``*AUTH*`` 会误伤无害字段，``SOCK`` 也不专属于凭据，因此这里使用精确名称。
        "SSH_AUTH_SOCK",
    }
)


# 仅保留查找命令、常规主目录和临时目录、启动 Windows 进程，以及本地化和终端行为
# 所需的变量。此处使用精确名称；应用配置、凭据、代理和未知的新变量必须由请求显式注入。
_INHERITED_ENV_ALLOWLIST: frozenset[str] = frozenset(
    {
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "SYSTEMROOT",
        "WINDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "TMP",
        "TEMP",
        "TMPDIR",
        "PWD",
        "SHELL",
        "VIRTUAL_ENV",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NUMERIC",
        "LC_TIME",
        "TERM",
        "COLORTERM",
    }
)


def _is_allowlisted_env_name(name: str) -> bool:
    """按宿主平台的环境变量大小写语义匹配精确白名单。"""
    candidate = name.upper() if os.name == "nt" else name
    return candidate in _INHERITED_ENV_ALLOWLIST


def is_blocked_env_name(name: str) -> bool:
    """分类配置投影中类似凭据的字段名称。"""
    upper = name.upper()
    if upper in _BLOCKED_EXACT_NAMES:
        return True
    return any(fnmatch.fnmatchcase(upper, pattern) for pattern in _SECRET_NAME_PATTERNS)


def build_sandbox_env(injected: dict[str, str] | None = None) -> dict[str, str]:
    """构造沙箱子进程环境：先继承精确白名单，再合并显式注入的请求值。

    注入值即使名称不在白名单中也会保留，因为该请求值已由调用链授权；此操作不会自动
    复制 Gateway 中的同名变量。
    """
    env = {key: value for key, value in os.environ.items() if _is_allowlisted_env_name(key)}
    if injected:
        env.update(injected)
    return env
