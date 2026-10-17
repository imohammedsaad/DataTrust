"""Environment-configured Exasol connectivity and readiness probe."""

from __future__ import annotations

import os
import ssl
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class ExasolConfigurationError(ValueError):
    """Required Exasol connection settings are missing or invalid."""


class ExasolDriverUnavailableError(RuntimeError):
    """The PyExasol runtime dependency is unavailable."""


class ExasolConnectionError(ConnectionError):
    """The service could not establish an Exasol connection."""


class ExasolQueryError(RuntimeError):
    """The Exasol health query failed."""


class ExasolStatement(Protocol):
    def fetchone(self) -> Any: ...


class ExasolConnection(Protocol):
    def execute(self, query: str) -> ExasolStatement: ...

    def close(self) -> None: ...


ConnectFactory = Callable[..., ExasolConnection]


@dataclass(frozen=True)
class ExasolSettings:
    dsn: str
    user: str
    password: str = field(repr=False)
    connection_timeout: int = 10
    socket_timeout: int = 30
    tls_ca_cert: str | None = None

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> ExasolSettings:
        """Load settings from the process environment (or a supplied mapping)."""
        source = os.environ if environ is None else environ
        required_names = ("EXASOL_DSN", "EXASOL_USER", "EXASOL_PASSWORD")
        missing = [
            name
            for name in required_names
            if not source.get(name) or not source[name].strip()
        ]
        if missing:
            names = ", ".join(missing)
            raise ExasolConfigurationError(
                f"Missing required Exasol environment variables: {names}"
            )

        return cls(
            dsn=source["EXASOL_DSN"].strip(),
            user=source["EXASOL_USER"].strip(),
            password=source["EXASOL_PASSWORD"],
            connection_timeout=_positive_timeout(
                source, "EXASOL_CONNECTION_TIMEOUT", default=10
            ),
            socket_timeout=_positive_timeout(
                source, "EXASOL_SOCKET_TIMEOUT", default=30
            ),
            tls_ca_cert=_optional_value(source, "EXASOL_TLS_CA_CERT"),
        )


def _positive_timeout(
    environ: Mapping[str, str], name: str, *, default: int
) -> int:
    raw_value = environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        raise ExasolConfigurationError(
            f"{name} must be a positive integer"
        ) from None
    if value <= 0:
        raise ExasolConfigurationError(f"{name} must be a positive integer")
    return value


def _optional_value(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    return value.strip() if value and value.strip() else None


def _pyexasol_connect(**kwargs: Any) -> ExasolConnection:
    try:
        import pyexasol
    except ImportError:
        raise ExasolDriverUnavailableError(
            "PyExasol is not installed; install backend/requirements.txt"
        ) from None

    return pyexasol.connect(**kwargs)


class ExasolDatabase:
    """Small injectable service for opening Exasol connections and probing them."""

    def __init__(
        self,
        settings: ExasolSettings,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self._settings = settings
        self._connect_factory = (
            connect_factory if connect_factory is not None else _pyexasol_connect
        )

    def health_check(self) -> bool:
        """Execute SELECT 1; return True only when Exasol returns the expected row."""
        try:
            connection = self._connect_factory(
                dsn=self._settings.dsn,
                user=self._settings.user,
                password=self._settings.password,
                connection_timeout=self._settings.connection_timeout,
                socket_timeout=self._settings.socket_timeout,
                encryption=True,
                websocket_sslopt=self._ssl_options(),
            )
        except ExasolDriverUnavailableError:
            raise ExasolDriverUnavailableError(
                "PyExasol is not installed; install backend/requirements.txt"
            ) from None
        except Exception:
            raise ExasolConnectionError(
                "Unable to connect to Exasol; verify the configured endpoint, "
                "network access, and credentials"
            ) from None

        query_error: ExasolQueryError | None = None
        try:
            row = connection.execute("SELECT 1").fetchone()
            if row is None or not row or row[0] != 1:
                query_error = ExasolQueryError(
                    "Exasol health query returned an unexpected result"
                )
        except Exception:
            query_error = ExasolQueryError(
                "Exasol connection succeeded, but the health query failed"
            )

        try:
            connection.close()
        except Exception:
            if query_error is None:
                raise ExasolQueryError(
                    "Exasol health query succeeded, but the connection "
                    "could not be closed"
                ) from None
            query_error = ExasolQueryError(
                "Exasol health query and connection cleanup failed"
            )

        if query_error is not None:
            raise query_error from None
        return True

    def _ssl_options(self) -> dict[str, Any] | None:
        if self._settings.tls_ca_cert is None:
            return None
        return {
            "cert_reqs": ssl.CERT_REQUIRED,
            "ca_certs": self._settings.tls_ca_cert,
        }


def main() -> int:
    try:
        ExasolDatabase(ExasolSettings.from_env()).health_check()
    except (
        ExasolConfigurationError,
        ExasolDriverUnavailableError,
        ExasolConnectionError,
        ExasolQueryError,
    ) as error:
        print(f"Exasol health check failed: {error}", file=sys.stderr)
        return 1
    print("Exasol health check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
