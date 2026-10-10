# Issue #45 — TEST precomputed report snapshots

2026-10-10. [PR #46](https://github.com/hungtranbkit/mesflow/pull/46).
Fresh worktree `mesflow-issue45`, branch `feat/45-precomputed-snapshots`, initially
from main `1dca8df`, then merged main `c2d3b46`. Runtime source `79eb346`;
final integration/test source `80fc547`. No production deployment.

## Deployed artifacts

Target: `vps-78ae7aec`, `148.113.207.13`, verified `PRODUCTION_TEST`.
Only the isolated report compose was changed; app, public support, nginx
container start times/images and nginx config hash stayed unchanged.

| Service | Image | Immutable image ID |
| --- | --- | --- |
| Reports | `mesflow-report-assistant:79eb346` | `sha256:72c8d5a786036285f2fdb6890a1e9fa8b395f01b2be2e2f5acbe428f482d42bb` |
| Worker/scope | `mesflow-report-snapshots:79eb346` | `sha256:9c07cc13044ba2239869f9f0e00b0969c37d784dde1ab10d28580315c5f2595f` |

Both containers healthy, read-only root filesystems, no published host ports,
0.5 CPU / 256MiB each. Snapshot directory 0700, files 0600; reports mount it
read-only and have neither database credentials nor the MES session signing key.
Root-only env files hold the restricted worker DSN and private scope key.

## Behavior and security

The worker prepares private daily partitions for 93 business dates before
questions. Reports refresh every 60s (TTL 150s); active sessions every 20s
(TTL 60s). Custom queries combine partitions. No request-time business API query
or export rebuild; only current session/permission and current-role checks are
live. Cold/stale/corrupt/future/unknown-schema sources fail closed with 503;
worker recovery publishes atomically. Watermark is batch read time, not an event
sequence. No migration or business DML on TEST. Dedicated-role security DDL,
private files, report audit and existing-session verification were required.

Five productivity filter cases and all five report types matched existing live
source API semantics. Unrounded additive score statistics preserve SQL AVG;
current PO planned/done values remain distinct from period session facts.
The exceptions worker reads repository SQL, avoiding the mutating exceptions
HTTP endpoint. Scan/freshness and real role-change tests use disposable local
PostgreSQL only; no synthetic scan or role change was written on TEST.

The existing backend can retain an old role in a signed login after a downgrade.
Every report operation additionally verifies current role/active/password state
through a private token-protected checker. Real PostgreSQL integration verifies
preview, download, chat facts and active facts deny after downgrade. The checker
has SELECT on only four `users` columns; TEST proof confirms no full users,
password or username access, no work-session UPDATE, and read-only default.
Missing/wrong scope tokens both return 403. This protects reports; canonical
app authorization is a separate owner follow-up, not fixed by this PR.

Local chat endpoints expose minimal aggregate facts with
`external_ai_allowed:false`; no business facts, identifiers, PII or credentials
were sent to the AI Gateway/public support. Contract coordinated with #39/#43,
public product Q&A #40/#44 and separate export engine #34. Existing #34 live
export engine is unchanged. The actual authenticated TEST app was version
`71.0.0.383` / `4fb2882`, with no chat button at desktop/mobile widths; #43/#34
were notified. This is API readiness, not a claim that the app widget is wired.

## Verification

- 52 focused Python tests; 3 real PostgreSQL snapshot/parity/security tests.
- Six focused Playwright checks for live/demo layouts, stale/session handling,
  freshness and PDF download. Native container PDF verified for Vietnamese text,
  valid signature, bounded rendering and literal HTML/file-injection input.
- Actual TEST browser: authenticated 1366px/390px; anonymous demo 320px. No
  overflow/page errors or browser business-data API calls. Desktop XLSX/CSV/PDF
  and mobile CSV all downloaded; all four SHA-256 values matched granted audit
  entries and their original source snapshot SHA. Audits omit rows/credentials.
- Anonymous root 200, app 302, auth/live preview/chat facts/active facts 401.
- Final full CI: [PR run 38029108233](https://github.com/hungtranbkit/mesflow/actions/runs/38029108233) passed on
  `80fc547`: **2,015 Python/PostgreSQL + 600 browser passed, 31 skipped**
  (27 Python, four browser). [Push run 38029105260](https://github.com/hungtranbkit/mesflow/actions/runs/38029105260)
  also passed with the same totals.

## Measured latency

Final private TEST candidate, 20 warm fact queries including signed-session and
current-role checks: p50 **87.76ms**, p95 **101.19ms** (inside TEST network).

Public authenticated browser, 20 successive preview submissions spaced 12s:

| Measurement | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Click → visible preview | 420.77ms | 851.21ms | 914.04ms |
| Browser API request | 369.43ms | 786.15ms | 835.84ms |

All 20 used precomputed sources across **five background generations**. Source
age ranged **1.4–59.3s**, with no page errors. Idle measurement: reports
44.1MiB / worker 33.68MiB, each under its 256MiB limit.

The browser measurement includes public network and browser UI work; it is not
comparable directly to the inside-TEST fact-query measurement. It measures
report preview, not AI response generation or PDF rendering. The baseline old
service's five HTTP requests measured p50 398ms / p95 403ms; different sample
size/path, so no universal speedup percentage is claimed. The main guarantee is
that questions use prepared sources and never trigger database report exports.

## Rollback and limits

Safe rollback disables only the report service and worker, preserving all
business services, nginx, private files and audit. Do not restore the old report
image: it lacks current-role verification. Pinned recovery starts the worker,
checks snapshot/scope health, then starts reports and checks health.

On TEST, as root:

```sh
python3 /opt/mesflow/report-assistant/rollback/issue45-20261010T0515Z/rollback.py check
python3 /opt/mesflow/report-assistant/rollback/issue45-20261010T0515Z/rollback.py disable
python3 /opt/mesflow/report-assistant/rollback/issue45-20261010T0515Z/rollback.py recover
```

The guarded **disable + recover exercise passed on TEST**. Both services stopped,
recovered to the exact pinned images and passed health. Authenticated preview,
chat facts and active facts then returned 200 with fresh snapshots; public root
returned 200. App/support/nginx container start times/images and nginx config
hash stayed unchanged throughout.

Filters span at most 31 days within the 93-day retained history; previews at
most 500 rows, native PDF 200 rows. Larger sources/outputs fail visibly without
silent truncation. Two published files each max 24MiB; interrupted temp files
are reaped. This deployment follows the existing single-workshop scope, not
multi-tenant isolation. Download grants last five minutes and freeze exact rows;
if the source ages beyond TTL, export metadata accurately labels it stale.

Sanitized raw proof is on HP under `/tmp/mesflow-issue45-evidence/`:
`scope-candidate-proof.json`, `scope-switch-proof.json`, `live-browser-proof.json`,
`browser-benchmark-proof.json`, `audit-security-proof.json`, `grants-proof.json`,
`rollback-safe-exercise.json`, `scope-integration-final.log`, `ci-final-pr.log`.
Sanitized proof is also preserved as `sanitized-test-proof.tar.gz` alongside
the deployment backup/proof on TEST under
`/opt/mesflow/report-assistant/rollback/issue45-20261010T0515Z/`.
Business exports/screenshots and temporary auth state are private, not attached
to GitHub or this document; temporary verification cookies are deleted after use.
