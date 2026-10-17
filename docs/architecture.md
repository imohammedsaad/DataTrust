# DataTrust architecture

## Purpose and scope

DataTrust is an incident-investigation workflow for data reliability problems. The first end-to-end slice is a daily record-volume check for a synthetic orders dataset: detect an abnormal volume, quantify it against history, expose evidence, show downstream impact, recommend a bounded investigation step, and let a user re-run the check to verify recovery.

This document and `contracts/openapi.yaml` establish a shared starting point before feature implementation. They are proposals for team review, not a claim that the product or database is already implemented. Details marked **decision required** must be agreed by both owners before they are encoded in backend and frontend behavior.

## Minimal architecture

```text
React + TypeScript + Vite
          | HTTP, contracts/openapi.yaml
          v
FastAPI application
  - API and response validation
  - check orchestration and deterministic diagnostic rules
  - repositories and Exasol connection management
          | supported Exasol Python driver
          v
Exasol Personal
  - synthetic source records
  - dataset and downstream-asset metadata
  - check-run and incident history
  - SQL aggregations, historical comparisons, joins, reconciliation
```

The browser talks only to FastAPI. FastAPI owns validation, orchestration, and conversion of SQL results into the API contract. Exasol is the analytical database and performs the comparisons and joins; Python must not replace those computations with hardcoded demo values. Diagnostic rules are deterministic and explainable. They may report a hypothesis only when returned evidence supports it, and should say when evidence is insufficient.

Keep the MVP synchronous: a check request runs its SQL and persists its result before returning. A background queue, scheduler, and distributed services are outside the initial scope.

## Investigation data flow

1. The UI lists open incidents and requests an incident's details from the API.
2. A user starts or re-runs a check for a dataset and target date.
3. FastAPI validates the request, obtains an Exasol connection from environment-based configuration, and calls repository queries.
4. Exasol aggregates target-period source records, compares the result with the configured historical baseline, and joins dataset dependencies to downstream business assets. SQL also performs source reconciliation when the check uses multiple sources.
5. FastAPI evaluates the returned measurements with deterministic rules, records a check run and any incident state change, then returns the run and linked incident identifiers.
6. The UI loads the incident detail, showing measurements, baseline period, supporting evidence, cautious hypothesis, affected assets, and recommended action.
7. A later check records a new run. A passing run can resolve the open incident and is linked to it in `resolved_incident_ids`; the UI can then show recovery and the latest check.

Every displayed analytic measurement must trace to a check-run result from the database. Seed data is synthetic and reproducible, and demo behavior must be produced by running the same check path as ordinary behavior.

## Initial data concepts

The following are logical entities; Person A owns their physical representation in Exasol. Exact columns and keys are subject to schema design.

| Entity | Purpose |
|---|---|
| `dataset` | Dataset identity, display name, metric/check configuration, and applicable time zone |
| `source_record` | Synthetic source-level facts used by the analytical checks |
| `downstream_asset` | A report or other business output affected by a monitored dataset |
| `asset_dependency` | Relationship between a dataset and downstream asset |
| `check_run` | Immutable record of a check execution, including target/baseline periods, measurements, rule outcome, and time |
| `incident` | Investigation record for a detected issue, its status, diagnostic evidence, and affected assets |

Incident evidence should retain the measured values and rule identifiers behind the finding, not just rendered prose. A run should be auditable independently of the UI. Database normalization, retention, and whether evidence is stored as columns or structured payloads are implementation decisions for Person A.

## Analytics and diagnostic boundaries

For the initial volume check, SQL in Exasol should:

- Aggregate source records by dataset, source, and target date.
- Aggregate historical observations over an agreed comparison window and calculate the baseline.
- Join observed and baseline aggregates to produce the comparison inputs.
- Join dataset dependencies to report affected downstream assets.
- Reconcile source counts or totals when multiple relevant sources exist.

Python applies versioned, deterministic rules to the SQL results (for example, a configured volume-deviation rule) and formats evidence and recommendations. SQL returns the actual values used. A diagnostic hypothesis is a rule-based possibility, never a verified root cause unless the evidence actually establishes one. The recommendation is an investigation step, not an automated repair.

**Decision required before implementation:** baseline definition (window and comparable-day policy), dataset time-zone and day-boundary semantics, minimum history required, zero-baseline handling, thresholds, severity mapping, source-reconciliation semantics, and incident deduplication/reopening behavior. These policy choices change the analytical results and must not be guessed independently by either owner.

## API contract

`contracts/openapi.yaml` is the shared source of truth for the initial HTTP boundary. It defines health checks, incident listing/detail, synchronous check creation, check-run retrieval, and common error responses. Both owners must agree on changes to this file before changing API behavior.

The proposed check request identifies a dataset and an ISO calendar date. The service selects the baseline according to agreed server-side policy; clients do not submit arbitrary analytic results or thresholds. Each request creates a new check run. The result can identify a newly detected/current incident or existing incidents resolved by that run. Incident and check-run response schemas expose explicit baseline/observed values, evidence, and affected assets; they do not assert an unsupported cause.

The contract is intentionally limited to the demonstration workflow. It does not define dataset administration, authentication, pagination, alerting, or asynchronous execution.

## Ownership boundaries

| Owner | Owned files |
|---|---|
| Person A | `backend/`, `sql/`, `data/`, and backend tests under `backend/tests/` |
| Person B | `frontend/`, including frontend tests |
| Shared | `contracts/`; both review and agree on contract changes |
| Agreement required | Root configuration/dependency files and deployment configuration |
| Shared documentation | `docs/architecture.md`; update it when an agreed architectural decision changes |

Each owner may consume the agreed contract but must not silently redefine it or edit the other owner's implementation area. Changes to root dependencies/configuration require agreement.

## Implementation plan and dependencies

| Step | Work | Owner | Depends on |
|---|---|---|---|
| 1 | Review and agree on this architecture, API schemas, baseline semantics, thresholds, incident lifecycle, and demo dataset/time zone | Both | None |
| 2 | Verify Exasol Personal availability, Python compatibility, and supported driver connection from the demo environment | Person A | 1 |
| 3 | Implement Exasol schema and deterministic synthetic history for the agreed incident and recovery scenario | Person A | 1, 2 |
| 4 | Implement analytical SQL and backend orchestration, persistence, API, and backend unit/integration tests | Person A | 1, 2, 3 |
| 5 | Implement the incident overview/detail and re-run/recovery UI with frontend tests | Person B | 1; can proceed alongside 2–4 using the contract |
| 6 | Integrate and rehearse the same seeded incident-to-recovery scenario end to end | Both | 4, 5 |

Do not start separate feature implementation before steps 1 and 2 settle the shared behavioral and connectivity assumptions.

## Testing and demonstration

- Backend unit tests cover rule outcomes, evidence requirements, percentage/zero-baseline handling, and incident state transitions.
- Backend integration tests execute the analytical SQL and persistence against a configured Exasol Personal instance. Mark/gate them so a missing database is reported as an unavailable integration environment, not mistaken for a passing database test.
- Synthetic seed generation is deterministic and idempotent or has a documented clean-and-reseed procedure.
- Frontend tests cover list/detail rendering, baseline and evidence visibility, downstream impact, loading/error states, and re-run/recovery behavior using contract-shaped API fixtures.
- The manual demo seeds history with one deliberately low-volume target day and normal comparison days; it runs the check, inspects evidence and impacted report, then checks a normal/recovered period and shows the resolved incident. Both results must be produced by Exasol-backed checks, not UI fixtures or hardcoded backend responses.

## Deployment and connectivity assumptions

The application development host is Windows 11, but no Exasol endpoint or instance is configured or verified there. Docker Desktop is running without an Exasol image/container. Exasol's `docker-db` repository describes its Docker image as a testing project, supports Docker only on Linux, and directs Windows-host users to use a Linux VM; do not treat it as a supported native Windows Personal deployment. The Exasol deployment owner must confirm the actual Personal deployment type, reachable DSN, database version, and network/firewall access before a live connection is attempted. See `docs/exasol-connectivity.md` for the verified host state and smoke-test procedure.

Connection credentials and host settings are supplied through environment variables; no secret belongs in Git. The backend uses PyExasol 3.0.0, whose current documentation requires Python 3.10+ and Exasol 8+. Python 3.12.5 is present on the development host, but compatibility with the target database remains unverified until its version is provided. PyExasol uses TLS encryption and certificate verification by default; the CA certificate requirement depends on the deployment. Readiness reports database connectivity separately from process liveness. Production authentication, secret-management service, migrations, backups, and operational monitoring are postponed with production deployment.

## Explicitly postponed

Additional anomaly types, arbitrary check configuration, scheduled/background execution, notifications, user accounts/roles, LLM explanations, automatic remediation, production deployment, and advanced dashboards are out of MVP scope. Revisit only after the initial investigation and recovery flow is demonstrable.
