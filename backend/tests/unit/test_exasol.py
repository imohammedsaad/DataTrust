import ssl
from collections.abc import Mapping
from unittest.mock import Mock

import pytest

from backend.app.db.exasol import (
    ExasolConfigurationError,
    ExasolConnectionError,
    ExasolDatabase,
    ExasolDriverUnavailableError,
    ExasolQueryError,
    ExasolSettings,
)


def settings(
    overrides: Mapping[str, str] | None = None,
) -> ExasolSettings:
    values = {
        "EXASOL_DSN": "db.example.invalid:8563",
        "EXASOL_USER": "service_user",
        "EXASOL_PASSWORD": "not-a-real-password",
    }
    if overrides:
        values.update(overrides)
    return ExasolSettings.from_env(values)


def test_settings_require_endpoint_user_and_password() -> None:
    with pytest.raises(ExasolConfigurationError, match="EXASOL_DSN"):
        ExasolSettings.from_env({})

    with pytest.raises(ExasolConfigurationError, match="EXASOL_PASSWORD"):
        ExasolSettings.from_env(
            {"EXASOL_DSN": "db.example.invalid:8563", "EXASOL_USER": "user"}
        )


def test_settings_parse_timeouts_and_optional_ca_certificate() -> None:
    config = settings(
        {
            "EXASOL_CONNECTION_TIMEOUT": "4",
            "EXASOL_SOCKET_TIMEOUT": "12",
            "EXASOL_TLS_CA_CERT": "certs/exasol-ca.pem",
        }
    )

    assert config.connection_timeout == 4
    assert config.socket_timeout == 12
    assert config.tls_ca_cert == "certs/exasol-ca.pem"
    assert "not-a-real-password" not in repr(config)


@pytest.mark.parametrize("value", ["0", "-2", "invalid"])
def test_settings_reject_invalid_timeouts(value: str) -> None:
    with pytest.raises(ExasolConfigurationError):
        settings({"EXASOL_CONNECTION_TIMEOUT": value})


def test_health_check_executes_query_and_closes_connection() -> None:
    statement = Mock()
    statement.fetchone.return_value = (1,)
    connection = Mock()
    connection.execute.return_value = statement
    connect = Mock(return_value=connection)

    result = ExasolDatabase(settings(), connect).health_check()

    assert result is True
    connect.assert_called_once_with(
        dsn="db.example.invalid:8563",
        user="service_user",
        password="not-a-real-password",
        connection_timeout=10,
        socket_timeout=30,
        encryption=True,
        websocket_sslopt=None,
    )
    connection.execute.assert_called_once_with("SELECT 1")
    connection.close.assert_called_once_with()


def test_health_check_passes_configured_ca_certificate_to_driver() -> None:
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (1,)
    connect = Mock(return_value=connection)

    ExasolDatabase(
        settings({"EXASOL_TLS_CA_CERT": "certs/ca.pem"}), connect
    ).health_check()

    assert connect.call_args.kwargs["websocket_sslopt"] == {
        "cert_reqs": ssl.CERT_REQUIRED,
        "ca_certs": "certs/ca.pem",
    }


def test_connection_failure_is_sanitized() -> None:
    connect = Mock(side_effect=RuntimeError("leaked not-a-real-password"))

    with pytest.raises(ExasolConnectionError) as error:
        ExasolDatabase(settings(), connect).health_check()

    assert "not-a-real-password" not in str(error.value)
    assert error.value.__cause__ is None


def test_missing_driver_is_reported_without_driver_error_details() -> None:
    connect = Mock(side_effect=ExasolDriverUnavailableError("module path details"))

    with pytest.raises(ExasolDriverUnavailableError) as error:
        ExasolDatabase(settings(), connect).health_check()

    assert "module path details" not in str(error.value)
    assert error.value.__cause__ is None


def test_query_failure_is_sanitized_and_connection_is_closed() -> None:
    connection = Mock()
    connection.execute.side_effect = RuntimeError("not-a-real-password")
    connect = Mock(return_value=connection)

    with pytest.raises(ExasolQueryError) as error:
        ExasolDatabase(settings(), connect).health_check()

    assert "not-a-real-password" not in str(error.value)
    assert error.value.__cause__ is None
    connection.close.assert_called_once_with()


def test_unexpected_health_result_is_reported_and_connection_is_closed() -> None:
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (0,)

    with pytest.raises(ExasolQueryError, match="unexpected result"):
        ExasolDatabase(settings(), Mock(return_value=connection)).health_check()

    connection.close.assert_called_once_with()


def test_connection_close_failure_is_reported_without_driver_details() -> None:
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (1,)
    connection.close.side_effect = RuntimeError("not-a-real-password")

    with pytest.raises(ExasolQueryError, match="could not be closed") as error:
        ExasolDatabase(settings(), Mock(return_value=connection)).health_check()

    assert "not-a-real-password" not in str(error.value)
