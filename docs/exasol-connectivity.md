# Exasol connectivity

## Verified runtime and deployment status

The checked development host is Windows 11 with Python 3.12.5 and Docker Desktop. Docker is running, but the local image/container inventory contains no Exasol image or instance. No `EXASOL_*` environment variables are configured, and PyExasol was not installed before this change. Therefore, there is no verified Exasol endpoint or credential set and no live database connection has been tested.

The official Exasol `docker-db` repository describes its image as a testing project, says Docker is supported only on Linux, and directs Windows-host users to create a Linux VM. It is not treated here as a supported Windows-host Personal deployment, and this change does not start or modify any container. The deployment owner must provide the actual Exasol Personal endpoint reachable from the backend runtime, its database version, credentials, and TLS certificate/trust requirements. Do not infer a host, port, password, or Docker port mapping.

## Driver and connection behavior

This layer uses **PyExasol 3.0.0**, pinned in `backend/requirements.txt`. Exasol's maintained PyExasol documentation identifies it as the officially supported Python connector. The current getting-started guide requires Python 3.10+ and Exasol 8+, while the project's README still states Exasol 7.1+; treat this documentation difference as unresolved and verify the selected Personal release against its compatibility notes. Python 3.12.5 on this host meets the documented Python requirement, but Exasol compatibility cannot be confirmed until the target Personal version is known.

The documented API is `pyexasol.connect(dsn=..., user=..., password=...)`; the driver returns a connection whose `execute("SELECT 1").fetchone()` runs a query. It supports connection and socket timeouts. PyExasol documentation states TLS encryption is enabled by default and certificate verification is enabled by default. The implementation explicitly keeps encryption on and requires certificate verification, optionally using the CA certificate at `EXASOL_TLS_CA_CERT` when the deployment uses a private CA. It does not disable TLS or certificate validation.

For an on-premises/Docker-style database, PyExasol documents database username/password authentication. It also documents access/refresh-token authentication for Exasol SaaS; this implementation intentionally does not add token auth because the target environment is Exasol Personal and its deployment-specific authentication has not yet been supplied. Obtain credentials from the instance owner; never use assumed example/default credentials.

Configuration is read from process environment variables:

| Variable | Required | Meaning |
|---|---:|---|
| `EXASOL_DSN` | Yes | Endpoint DSN supplied by the deployment owner |
| `EXASOL_USER` | Yes | Database login supplied by the deployment owner |
| `EXASOL_PASSWORD` | Yes | Database password supplied securely |
| `EXASOL_CONNECTION_TIMEOUT` | No | Positive seconds; defaults to 10 |
| `EXASOL_SOCKET_TIMEOUT` | No | Positive seconds; defaults to 30 |
| `EXASOL_TLS_CA_CERT` | No | Path to a CA certificate file if required |

`.env.example` contains placeholders only. The application reads the environment; it does not automatically load a `.env` file. Keep actual secrets in the shell/process environment or an approved secret manager, and do not commit them. Error messages are sanitized; connection and query exception details from the driver are not forwarded.

## Install and run a real-instance smoke test

From the repository root, install the backend dependency:

```powershell
python -m pip install -r backend\requirements.txt
```

Set the actual endpoint and credentials securely in the current PowerShell session, and set a CA path only if needed by the deployment:

```powershell
$env:EXASOL_DSN = Read-Host "Exasol DSN"
$env:EXASOL_USER = Read-Host "Exasol username"
$securePassword = Read-Host -AsSecureString "Exasol password"
$env:EXASOL_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
# Optional: $env:EXASOL_TLS_CA_CERT = "<path-to-deployment-ca-certificate>"
python -m backend.app.db.exasol
Remove-Item Env:EXASOL_PASSWORD
```

The command succeeds only after it connects and executes `SELECT 1`, printing `Exasol health check passed.` Missing settings, an unavailable driver, connection failures, and query failures produce a sanitized error and a nonzero exit status. Do not paste credentials into shared logs or command history; prefer setting them through the local secret manager or IDE run configuration for a real deployment.

## Official references

- [PyExasol Getting Started](https://exasol.github.io/pyexasol/master/user_guide/getting_started.html) — supported Python/database requirements and query example.
- [PyExasol API Reference](https://exasol.github.io/pyexasol/master/api.html#pyexasol.connect) — `connect` arguments, timeout settings, and TLS option.
- [PyExasol Security Guide](https://exasol.github.io/pyexasol/master/user_guide/configuration/security.html) — password/token authentication, TLS encryption, and certificate verification behavior.
- [PyExasol 3.0.0 release notes](https://exasol.github.io/pyexasol/master/changes/changes_3.0.0.html) — current documented version.
- [Exasol docker-db repository](https://github.com/exasol/docker-db) — testing purpose, Linux/Windows VM constraints, and connection notes for that image.
- [Exasol on-premises system requirements](https://docs.exasol.com/db/latest/administration/on-premise/installation/system_requirements.htm) — server platform requirements.
