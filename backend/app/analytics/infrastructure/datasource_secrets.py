"""`env://` 凭证解析器：把不透明的 `secret_ref` 变成一次性连接材料，并把 TLS 收敛到两个可选值。

为什么这样设计：

- 引用规则只认 `env://[A-Z][A-Z0-9_]*`，DSN、文件路径、Vault/云 secret 形式因此根本进不了解析路径，
  不需要"先识别再剥离"这类容易漏判的兼容逻辑；
- 环境变量内容必须是受限 JSON 对象而不是连接串：一旦接受连接串，host、用户名、密码就揉在一个字符串里，
  任何前缀重写或参数覆盖都可能绕过本模块的逐字段校验；
- credential 只在本模块内部流动，`repr`/`str` 全部隐藏，失败也只暴露稳定错误码，避免凭证经日志、SSE、
  plan receipt 或异常文本外泄；
- 明文（`tls_mode=disable`）只允许留在 loopback，离开本机就必须走系统信任根 + 主机名校验。
"""

import ipaddress
import json
import os
import re
import ssl
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import URL

from app.analytics.domain import DatasourceDefinition, DatasourceEngine

__all__ = [
    "DatasourceSecretError",
    "DatasourceSecretErrorCode",
    "DatasourceTlsMode",
    "EnvironmentDatasourceSecretResolver",
]

_REFERENCE_PATTERN = re.compile(r"env://([A-Z][A-Z0-9_]*)\Z")
_REQUIRED_KEYS = frozenset({"engine", "host", "port", "database", "username", "password"})
_OPTIONAL_KEYS = frozenset({"tls_mode", "ca_pem"})
_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS
_DRIVERNAME_BY_ENGINE = {
    DatasourceEngine.MYSQL: "mysql+asyncmy",
    DatasourceEngine.POSTGRESQL: "postgresql+asyncpg",
}
_LOOPBACK_HOSTNAMES = frozenset({"localhost"})
_DSN_SCHEME_MARKER = "://"
_DSN_MARKERS = (_DSN_SCHEME_MARKER, "?", "&", "=")
_HOST_FORBIDDEN_CHARACTERS = frozenset("/@?&=")
_MIN_PORT = 1
_MAX_PORT = 65535
# 对外只有这一条固定文本：错误码走 DatasourceSecretError.code，任何输入都不参与拼装。
_ERROR_MESSAGE = "datasource secret resolution failed"


class DatasourceSecretErrorCode(StrEnum):
    """稳定的失败种类；调用方只能依据它做决策，不能依赖异常文本。"""

    INVALID_DATASOURCE = "invalid_datasource"
    INVALID_REFERENCE = "invalid_reference"
    UNAVAILABLE = "unavailable"
    INVALID_PAYLOAD = "invalid_payload"
    ENGINE_MISMATCH = "engine_mismatch"
    TLS_NOT_ALLOWED = "tls_not_allowed"


class DatasourceTlsMode(StrEnum):
    """V1 只承认两种 TLS 语义，不存在"信任任意 CA 路径"的第三态。"""

    DISABLE = "disable"
    VERIFY_FULL = "verify_full"


class DatasourceSecretError(Exception):
    """凭证解析失败的对外异常：message 固定，细节仅通过 `code` 暴露。"""

    def __init__(self, code: DatasourceSecretErrorCode) -> None:
        super().__init__(_ERROR_MESSAGE)
        self.code = code


@dataclass(frozen=True, slots=True, repr=False)
class ResolvedDatasourceCredential:
    """已解析的连接材料，仅限 infrastructure 内部使用。

    字段含有 URL（内含密码）与 SSL 上下文，因此 repr/str 一律固定隐藏，绝不回显字段值。
    """

    engine: DatasourceEngine
    tls_mode: DatasourceTlsMode
    url: URL
    ssl_context: ssl.SSLContext | None

    def __repr__(self) -> str:
        return "<ResolvedDatasourceCredential redacted>"

    __str__ = __repr__


def _require_identifier(value: object) -> str:
    """标识符既不能为空，也不能带任何空白（含首尾填充与内部空格）。"""

    if not isinstance(value, str) or not value or value != value.strip() or any(character.isspace() for character in value):
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return value


def _require_locator(value: object) -> str:
    """locator（database/username）除标识符规则外，还拒绝 DSN 形状的字符串。"""

    locator = _require_identifier(value)
    if any(marker in locator for marker in _DSN_MARKERS):
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return locator


def _require_password(value: object) -> str:
    """密码是不透明材料：不做裁剪或规范化，只拒绝全空白值，以免悄悄改动口令。"""

    if not isinstance(value, str) or not value.strip():
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    if _DSN_SCHEME_MARKER in value:
        # 只拦 DSN 形状；"?"/"&"/"=" 是常见口令字符，不能因为形似查询串就误拒合法口令。
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return value


def _require_host(value: object) -> str:
    host = _require_identifier(value)
    if any(character in _HOST_FORBIDDEN_CHARACTERS for character in host):
        # 主机名只能是主机名或 IP 字面量；"/"、"@" 与 DSN 查询串字符会改变 URL 语义。
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return host


def _require_port(value: object) -> int:
    # bool 是 int 的子类，JSON true/false 必须被拒绝，而不是被当作 1/0。
    if not isinstance(value, int) or isinstance(value, bool) or not _MIN_PORT <= value <= _MAX_PORT:
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return value


def _require_engine(value: object) -> DatasourceEngine:
    engine_token = _require_identifier(value)
    try:
        return DatasourceEngine(engine_token)
    except ValueError:
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD) from None


def _require_tls_mode(value: object) -> DatasourceTlsMode:
    try:
        return DatasourceTlsMode(value)
    except ValueError:
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD) from None


def _require_ca_pem(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return value


def _decode_payload(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except ValueError:
        # JSONDecodeError 会把整份原始文本留在 .doc 上，显式 from None 断开异常链，
        # 避免环境变量内容经 __cause__/__context__ 进入 traceback。
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD) from None
    if not isinstance(payload, dict):
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    if set(payload) - _ALLOWED_KEYS or _REQUIRED_KEYS - set(payload):
        raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
    return payload


def _is_loopback_host(host: str) -> bool:
    if host.casefold() in _LOOPBACK_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # 解析不成 IP 的主机名一律按"非 loopback"处理：DNS 可以把它指向任意地址，
        # 只有明确的 loopback 字面量才允许明文。
        return False
    if address.is_loopback:
        return True
    # ::ffff:127.0.0.1 这类 IPv4-mapped 地址实际连到 IPv4 loopback 接口。
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped is not None and mapped.is_loopback


def _build_ssl_context(ca_pem: str | None) -> ssl.SSLContext:
    if ca_pem is None:
        context = ssl.create_default_context()
    else:
        try:
            context = ssl.create_default_context(cadata=ca_pem)
        except (ssl.SSLError, ValueError) as error:
            # ca_pem 只能是内存中的证书：路径字符串交给 OpenSSL 也只会得到 "no start line"，
            # 因此这里不会变成读文件的后门；异常链保留 OpenSSL 细节，其文本不含输入内容。
            raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD) from error
        # create_default_context(cadata=...) 只加载传入的 CA 并丢掉系统信任根；显式补回，
        # 保证 verify_full 的基础信任面始终是系统根，ca_pem 只是额外叠加。
        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    # 防御性重申：证书链与主机名校验必须开启，避免未来被"便于调试"改成不安全默认。
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class EnvironmentDatasourceSecretResolver:
    """V1 凭证解析：`env://NAME` -> 环境变量中的受限 JSON -> SQLAlchemy `URL` + SSL 上下文。"""

    def resolve(self, datasource: DatasourceDefinition) -> ResolvedDatasourceCredential:
        if not isinstance(datasource, DatasourceDefinition):
            raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_DATASOURCE)
        variable = self._variable_name(datasource.secret_ref)
        raw = os.environ.get(variable)
        if raw is None or not raw.strip():
            raise DatasourceSecretError(DatasourceSecretErrorCode.UNAVAILABLE)
        payload = _decode_payload(raw)
        engine = _require_engine(payload["engine"])
        if engine is not datasource.engine:
            # 引擎不一致通常意味着 secret_ref 指错了变量，静默按 datasource 口径连接会掩盖配置错误。
            raise DatasourceSecretError(DatasourceSecretErrorCode.ENGINE_MISMATCH)
        host = _require_host(payload["host"])
        database = _require_locator(payload["database"])
        username = _require_locator(payload["username"])
        password = _require_password(payload["password"])
        port = _require_port(payload["port"])
        tls_mode = _require_tls_mode(payload.get("tls_mode", DatasourceTlsMode.VERIFY_FULL.value))
        ca_pem = _require_ca_pem(payload["ca_pem"]) if "ca_pem" in payload else None
        if tls_mode is DatasourceTlsMode.DISABLE:
            if ca_pem is not None:
                # 明文下提供 CA 是矛盾配置：不接受"看起来更安全"的输入来掩盖实际关闭的校验。
                raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_PAYLOAD)
            if not _is_loopback_host(host):
                raise DatasourceSecretError(DatasourceSecretErrorCode.TLS_NOT_ALLOWED)
        ssl_context = None if tls_mode is DatasourceTlsMode.DISABLE else _build_ssl_context(ca_pem)
        # 一律通过 URL.create 组装：字符串拼接会引入转义与参数注入面。
        url = URL.create(
            drivername=_DRIVERNAME_BY_ENGINE[datasource.engine],
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
        )
        return ResolvedDatasourceCredential(engine=datasource.engine, tls_mode=tls_mode, url=url, ssl_context=ssl_context)

    @staticmethod
    def _variable_name(secret_ref: object) -> str:
        match = _REFERENCE_PATTERN.fullmatch(secret_ref) if isinstance(secret_ref, str) else None
        if match is None:
            raise DatasourceSecretError(DatasourceSecretErrorCode.INVALID_REFERENCE)
        return match.group(1)
