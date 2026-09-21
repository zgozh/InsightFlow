"""`env://` 凭证解析与 TLS 边界的契约测试。

这里真正要钉住的不是"解析成功"，而是三件安全事实：
1. 只接受受控的 `env://NAME` 引用，任何 DSN/文件路径/云 secret 形式都不进入解析；
2. `tls_mode` 只允许"本机明文"或"系统信任根 + 主机名校验"，不存在"信任任意 CA 路径"的入口；
3. 失败对外只有稳定错误码，环境变量内容、用户名、主机名与密码绝不进入异常文本或 repr。
"""

import json
import ssl

import pytest
from sqlalchemy import URL

import app.analytics.infrastructure as analytics_infrastructure
from app.analytics.domain import DatasourceDefinition, DatasourceEngine
from app.analytics.infrastructure import datasource_secrets
from app.analytics.infrastructure.datasource_secrets import (
    DatasourceSecretError,
    DatasourceSecretErrorCode,
    DatasourceTlsMode,
    EnvironmentDatasourceSecretResolver,
)

_ENV_NAME = "SALES_DB_SECRET"
_SECRET_REF = f"env://{_ENV_NAME}"
_HOST = "db.internal"
_PORT = 5432
_DATABASE = "analytics"
_USERNAME = "svc_reporting"
_PASSWORD = "secret-value"
# 固定的对外错误文本：实现把细节全部收敛到 code，异常 message 不允许插值任何输入。
_STABLE_ERROR_MESSAGE = "datasource secret resolution failed"

# 仅用于测试的自签名 CA 证书（公开材料，无私钥，2120 年过期）；用于验证 ca_pem 只以内存
# 证书形式叠加，测试本身不读取任何文件系统路径。
_SYNTHETIC_CA_COMMON_NAME = "InsightFlow Synthetic Test CA"
_SYNTHETIC_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIC8zCCAdugAwIBAgIUT8JOwiyB1lxDa6fIio0cjJDaK7cwDQYJKoZIhvcNAQEL
BQAwKDEmMCQGA1UEAwwdSW5zaWdodEZsb3cgU3ludGhldGljIFRlc3QgQ0EwIBcN
MjAwMTAxMDAwMDAwWhgPMjEyMDAxMDEwMDAwMDBaMCgxJjAkBgNVBAMMHUluc2ln
aHRGbG93IFN5bnRoZXRpYyBUZXN0IENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A
MIIBCgKCAQEAjDkykVPW3smScIVfSGdrm0x6RmArwjIOt1ZHZqvhKHskoZ8FG7qI
nUC5gKbcQRnpVzPGwKmil6swNsdXvYGzBxTdWQfIKgjFDwWuY6gTs8bGiiipZ1t8
CjAI9j+hWh2cm98pr66S/+wk49TmjTRrFKhi/iJjbnW9HfDGMuFNXcHyMc8ZNkBD
SfljnO03CB5LAoye0A7kh1Pn+4cQ9mPONNdnVTVF+X9fElTxBQhcsw0XgNLvBHEH
bIReou2uBYtxvfEqisPkZUO7flkszt88TCxkdAw1nTaHdY3WuyPQBIMkkv7vsJ42
qgtXpVYFVnf/vsfZjvmB6jLKondAu+GXrQIDAQABoxMwETAPBgNVHRMBAf8EBTAD
AQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAFXcxX1LeqBbDZUUZZRd7X0uAlKidipUk1
1DseRctmi7YBYFgImBQYA1TVaIyvGao6Jang8UqTGYpylJ3qFm/EY4fvKHcnrRfj
jDEU4o7Ggc+3tSCiOyR9dAjLpaU36KgbmcJMICj6htbF9beNVvWFghA0HCNBcxSN
T+JPAuXgamudohsBCO+yBed/HODfyY9v94D0UYEdTS8YM393bc240VbJ1ngewh0u
0VU7BHG5TrmR8yZzyuoctAIQfGh/3tmTnmLEWt3YOUr62VoI1lKso+rW9Wgaq5YW
g2jcD8Hc53YOafhq1yOJY+YiZC6teE9lLE/GzCO97PS91OBcngiZ
-----END CERTIFICATE-----
"""


def _datasource(*, engine: DatasourceEngine = DatasourceEngine.POSTGRESQL, secret_ref: str = _SECRET_REF) -> DatasourceDefinition:
    return DatasourceDefinition(
        id="sales-primary",
        owner_id="user-1",
        name="Sales warehouse",
        engine=engine,
        secret_ref=secret_ref,
    )


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "engine": "postgresql",
        "host": _HOST,
        "port": _PORT,
        "database": _DATABASE,
        "username": _USERNAME,
        "password": _PASSWORD,
        "tls_mode": "verify_full",
    }
    payload.update(overrides)
    return payload


def _set_content(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    monkeypatch.setenv(_ENV_NAME, json.dumps(payload))


def _resolve(monkeypatch: pytest.MonkeyPatch, payload: object, *, engine: DatasourceEngine = DatasourceEngine.POSTGRESQL):
    _set_content(monkeypatch, payload)
    return EnvironmentDatasourceSecretResolver().resolve(_datasource(engine=engine))


def _reject(monkeypatch: pytest.MonkeyPatch, payload: object, *, engine: DatasourceEngine = DatasourceEngine.POSTGRESQL) -> DatasourceSecretError:
    with pytest.raises(DatasourceSecretError) as caught:
        _resolve(monkeypatch, payload, engine=engine)
    return caught.value


def _trust_root_count() -> int:
    return ssl.create_default_context().cert_store_stats()["x509_ca"]


def _subject_texts(context: ssl.SSLContext) -> list[str]:
    return [str(certificate["subject"]) for certificate in context.get_ca_certs()]


# --- 引用形式 ---------------------------------------------------------------


def test_resolver_accepts_a_strict_uppercase_environment_reference(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload())

    assert isinstance(credential.url, URL)
    assert credential.url.drivername == "postgresql+asyncpg"
    assert credential.url.host == _HOST
    assert credential.url.port == _PORT
    assert credential.url.database == _DATABASE
    assert credential.url.username == _USERNAME
    assert credential.url.password == _PASSWORD
    assert credential.engine is DatasourceEngine.POSTGRESQL
    assert credential.tls_mode is DatasourceTlsMode.VERIFY_FULL
    assert credential.ssl_context is not None


def test_mysql_engine_resolves_to_the_asyncmy_driver(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload(engine="mysql"), engine=DatasourceEngine.MYSQL)

    assert credential.url.drivername == "mysql+asyncmy"
    assert credential.engine is DatasourceEngine.MYSQL


@pytest.mark.parametrize(
    "secret_ref",
    [
        "env://lowercase",
        "env://Mixed9",
        "env://1LEADING",
        "env://_LEADING",
        "env://HAS-DASH",
        "env://HAS SPACE",
        "env://HAS.DOT",
        "env://HAS/SLASH",
        "env://UPPER/nested",
        "env://",
        "env:/UPPER",
        "ENV://UPPER",
        "Env://UPPER",
        "vault://UPPER",
        "file:///etc/ssl/ca.pem",
        "s3://bucket/key",
        "postgresql://svc:secret-value@db.internal:5432/analytics",
        "UPPER",
        "env://UPPER=1",
    ],
)
def test_resolver_rejects_everything_outside_the_strict_uppercase_rule(monkeypatch: pytest.MonkeyPatch, secret_ref: str):
    _set_content(monkeypatch, _payload())

    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(_datasource(secret_ref=secret_ref))

    assert caught.value.code is DatasourceSecretErrorCode.INVALID_REFERENCE
    assert secret_ref not in str(caught.value)


def test_missing_environment_variable_is_reported_as_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(_ENV_NAME, raising=False)

    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(_datasource())

    assert caught.value.code is DatasourceSecretErrorCode.UNAVAILABLE


@pytest.mark.parametrize("content", ["", "   ", "\n"])
def test_blank_environment_content_is_reported_as_unavailable(monkeypatch: pytest.MonkeyPatch, content: str):
    monkeypatch.setenv(_ENV_NAME, content)

    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(_datasource())

    assert caught.value.code is DatasourceSecretErrorCode.UNAVAILABLE


def test_resolution_reads_the_environment_at_call_time(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(_ENV_NAME, raising=False)
    resolver = EnvironmentDatasourceSecretResolver()

    with pytest.raises(DatasourceSecretError):
        resolver.resolve(_datasource())

    _set_content(monkeypatch, _payload())
    assert resolver.resolve(_datasource()).url.host == _HOST


def test_non_datasource_input_is_rejected_with_a_stable_error():
    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(object())  # type: ignore[arg-type]

    assert caught.value.code is DatasourceSecretErrorCode.INVALID_DATASOURCE


# --- 环境变量内容形态 -------------------------------------------------------

_DSN_STRING = "postgresql://svc_reporting:secret-value@db.internal:5432/analytics"


@pytest.mark.parametrize(
    "content",
    [
        _DSN_STRING,
        json.dumps(_DSN_STRING),
        "mysql://svc_reporting:secret-value@db.internal:3306/analytics",
        "[]",
        json.dumps([1, 2, 3]),
        json.dumps("secret-value"),
        "5432",
        "{",
        "not json at all",
        "{}",
    ],
)
def test_environment_content_must_be_a_restricted_json_object(monkeypatch: pytest.MonkeyPatch, content: str):
    monkeypatch.setenv(_ENV_NAME, content)

    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(_datasource())

    assert caught.value.code is DatasourceSecretErrorCode.INVALID_PAYLOAD
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize("missing_key", ["engine", "host", "port", "database", "username", "password"])
def test_every_declared_key_is_required(monkeypatch: pytest.MonkeyPatch, missing_key: str):
    payload = _payload()
    del payload[missing_key]

    assert _reject(monkeypatch, payload).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize("extra_key", ["sslmode", "ca_path", "ca_file", "capath", "dsn", "url", "hostname", "options", "schema"])
def test_extra_json_keys_are_rejected(monkeypatch: pytest.MonkeyPatch, extra_key: str):
    error = _reject(monkeypatch, _payload(**{extra_key: "anything"}))

    assert error.code is DatasourceSecretErrorCode.INVALID_PAYLOAD
    assert "anything" not in str(error)


def test_engine_must_agree_with_the_datasource_definition(monkeypatch: pytest.MonkeyPatch):
    error = _reject(monkeypatch, _payload(engine="mysql"))

    assert error.code is DatasourceSecretErrorCode.ENGINE_MISMATCH
    assert "db.internal" not in str(error)

    assert _reject(monkeypatch, _payload(engine="postgresql"), engine=DatasourceEngine.MYSQL).code is DatasourceSecretErrorCode.ENGINE_MISMATCH


@pytest.mark.parametrize("engine_value", ["oracle", "postgres", "", " ", "POSTGRESQL", 42, None, True])
def test_unknown_engine_tokens_are_rejected(monkeypatch: pytest.MonkeyPatch, engine_value: object):
    assert _reject(monkeypatch, _payload(engine=engine_value)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", ""),
        ("host", "   "),
        ("host", f" {_HOST}"),
        ("host", f"{_HOST} "),
        ("host", "db internal"),
        ("host", "db.internal\n"),
        ("database", ""),
        ("database", "  "),
        ("database", f" {_DATABASE}"),
        ("username", ""),
        ("username", "  "),
        ("username", f"{_USERNAME} "),
        ("username", "svc reporting"),
    ],
)
def test_identifiers_must_be_non_blank_and_free_of_padding(monkeypatch: pytest.MonkeyPatch, field: str, value: str):
    assert _reject(monkeypatch, _payload(**{field: value})).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", _DSN_STRING),
        ("host", "db.internal/analytics"),
        ("host", "svc@db.internal"),
        ("database", _DSN_STRING),
        ("database", "analytics?sslmode=disable"),
        ("username", _DSN_STRING),
        ("password", _DSN_STRING),
    ],
)
def test_dsn_style_strings_are_never_accepted_inside_the_payload(monkeypatch: pytest.MonkeyPatch, field: str, value: str):
    error = _reject(monkeypatch, _payload(**{field: value}))

    assert error.code is DatasourceSecretErrorCode.INVALID_PAYLOAD
    assert "secret-value" not in str(error)


@pytest.mark.parametrize("port", ["5432", True, False, 0, -1, 65536, 5432.5, None, [5432], {"port": 5432}])
def test_port_must_be_a_plain_integer_in_range(monkeypatch: pytest.MonkeyPatch, port: object):
    assert _reject(monkeypatch, _payload(port=port)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize("port", [1, 65535, _PORT])
def test_port_range_boundaries_are_accepted(monkeypatch: pytest.MonkeyPatch, port: int):
    assert _resolve(monkeypatch, _payload(port=port)).url.port == port


@pytest.mark.parametrize("password", ["", "   ", 12345, None, True])
def test_password_must_be_a_non_blank_string(monkeypatch: pytest.MonkeyPatch, password: object):
    assert _reject(monkeypatch, _payload(password=password)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


# --- TLS 边界 ---------------------------------------------------------------


def test_tls_mode_defaults_to_verify_full(monkeypatch: pytest.MonkeyPatch):
    payload = _payload()
    del payload["tls_mode"]

    credential = _resolve(monkeypatch, payload)

    assert credential.tls_mode is DatasourceTlsMode.VERIFY_FULL
    assert credential.ssl_context is not None
    assert credential.ssl_context.check_hostname is True


def test_tls_mode_never_defaults_to_plaintext_even_on_loopback(monkeypatch: pytest.MonkeyPatch):
    payload = _payload(host="127.0.0.1")
    del payload["tls_mode"]

    credential = _resolve(monkeypatch, payload)

    assert credential.tls_mode is DatasourceTlsMode.VERIFY_FULL
    assert credential.ssl_context is not None


@pytest.mark.parametrize("tls_mode", ["require", "verify-ca", "verify_identity", "VERIFY_FULL", "Disable", "prefer", "", " ", None, True, 1])
def test_tls_mode_accepts_only_the_two_documented_values(monkeypatch: pytest.MonkeyPatch, tls_mode: object):
    assert _reject(monkeypatch, _payload(tls_mode=tls_mode)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize(
    "host",
    ["localhost", "LOCALHOST", "127.0.0.1", "127.0.0.53", "::1", "0:0:0:0:0:0:0:1", "::ffff:127.0.0.1"],
)
def test_disable_is_allowed_for_loopback_hosts(monkeypatch: pytest.MonkeyPatch, host: str):
    credential = _resolve(monkeypatch, _payload(host=host, tls_mode="disable"))

    assert credential.tls_mode is DatasourceTlsMode.DISABLE
    assert credential.ssl_context is None


@pytest.mark.parametrize(
    "host",
    ["db.internal", "example.com", "10.1.2.3", "0.0.0.0", "169.254.169.254", "::ffff:10.1.2.3", "localhost.evil.com", "127.0.0.1.evil.com", "[::1]"],
)
def test_disable_is_rejected_for_non_loopback_hosts(monkeypatch: pytest.MonkeyPatch, host: str):
    error = _reject(monkeypatch, _payload(host=host, tls_mode="disable"))

    assert error.code is DatasourceSecretErrorCode.TLS_NOT_ALLOWED
    assert host not in str(error)


def test_verify_full_uses_system_trust_roots_and_enables_hostname_verification(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload())
    context = credential.ssl_context

    assert context is not None
    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.cert_store_stats()["x509_ca"] >= _trust_root_count() > 0
    assert _SYNTHETIC_CA_COMMON_NAME not in " ".join(_subject_texts(context))


def test_verify_full_layers_the_in_memory_ca_pem_on_top_of_system_roots(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload(ca_pem=_SYNTHETIC_CA_PEM))
    context = credential.ssl_context

    assert context is not None
    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
    # 系统信任根仍然是基础：只叠加 ca_pem，不允许 ca_pem 取代系统校验。
    assert context.cert_store_stats()["x509_ca"] > _trust_root_count()
    assert any(_SYNTHETIC_CA_COMMON_NAME in subject for subject in _subject_texts(context))


@pytest.mark.parametrize(
    "ca_pem",
    [
        "C:\\certs\\corporate-ca.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "file:///etc/ssl/ca.pem",
        "not a certificate",
        "-----BEGIN CERTIFICATE-----\nsecret-value\n-----END CERTIFICATE-----",
    ],
)
def test_ca_pem_must_be_an_in_memory_certificate_and_never_a_file_path(monkeypatch: pytest.MonkeyPatch, ca_pem: str):
    error = _reject(monkeypatch, _payload(ca_pem=ca_pem))

    assert error.code is DatasourceSecretErrorCode.INVALID_PAYLOAD
    assert "secret-value" not in str(error)


@pytest.mark.parametrize("ca_pem", ["", "   ", 123, None, True])
def test_blank_ca_pem_values_are_rejected(monkeypatch: pytest.MonkeyPatch, ca_pem: object):
    assert _reject(monkeypatch, _payload(ca_pem=ca_pem)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


def test_ca_pem_is_rejected_when_tls_is_disabled(monkeypatch: pytest.MonkeyPatch):
    assert _reject(monkeypatch, _payload(host="127.0.0.1", tls_mode="disable", ca_pem=_SYNTHETIC_CA_PEM)).code is DatasourceSecretErrorCode.INVALID_PAYLOAD


# --- 泄漏面 -----------------------------------------------------------------


def test_repr_and_str_hide_every_credential_field(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload())

    text = f"{credential!r} {credential!s}"

    assert "password" not in repr(credential)
    assert _PASSWORD not in text
    assert _USERNAME not in text
    assert _HOST not in text
    assert _ENV_NAME not in text
    assert _SECRET_REF not in text


def test_url_never_renders_the_password(monkeypatch: pytest.MonkeyPatch):
    credential = _resolve(monkeypatch, _payload())

    assert _PASSWORD not in str(credential.url)
    assert _PASSWORD not in repr(credential.url)


@pytest.mark.parametrize(
    "payload",
    [
        _payload(host="db.internal", tls_mode="disable"),
        _payload(engine="mysql"),
        _payload(port="5432"),
        _payload(ca_pem="not a certificate"),
        _payload(extra_key="anything"),
    ],
)
def test_errors_never_contain_environment_content(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]):
    error = _reject(monkeypatch, payload)

    assert _PASSWORD not in str(error)
    assert _PASSWORD not in repr(error)
    assert _USERNAME not in str(error)
    assert _HOST not in str(error)
    assert _ENV_NAME not in str(error)
    assert _SECRET_REF not in str(error)


def test_error_message_is_a_fixed_stable_string(monkeypatch: pytest.MonkeyPatch):
    _set_content(monkeypatch, _payload(host="db.internal", tls_mode="disable"))
    with pytest.raises(DatasourceSecretError) as caught:
        EnvironmentDatasourceSecretResolver().resolve(_datasource())

    assert str(caught.value) == _STABLE_ERROR_MESSAGE
    assert caught.value.code is DatasourceSecretErrorCode.TLS_NOT_ALLOWED
    assert "secret-value" not in str(caught.value)


def test_error_codes_are_stable_snake_case_tokens():
    assert {code.value for code in DatasourceSecretErrorCode} == {
        "invalid_datasource",
        "invalid_reference",
        "unavailable",
        "invalid_payload",
        "engine_mismatch",
        "tls_not_allowed",
    }


def test_credential_type_stays_private_to_the_module():
    # 只约束 credential 不外泄：resolver/错误码本身允许在装配层被接线引用。
    assert "ResolvedDatasourceCredential" not in datasource_secrets.__all__
    assert not hasattr(analytics_infrastructure, "ResolvedDatasourceCredential")
