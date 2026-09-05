# Requirement ↔ Code Gaps

Confirmed mismatches between `docs/MESFLOW_MASTER_REQUIREMENTS.md` /
`_VI.md` and the real running code, found during the 2026-09-05 QC
package standardization audit. Format per gap: **Requirement says** /
**Code currently does** / **Risk** / **Recommended resolution**.
Gaps that are clearly wrong were corrected directly in the master docs
(see each entry's Resolution); gaps that are merely unconfirmed/unclear
are left as gaps, not guessed at.

---

## GAP-001 — Business API paths missing their `/api` prefix (CORRECTED)

- **Requirement says**: every Part B "Trigger" field shows a bare path,
  e.g. `GET /reports/employee-productivity`, `POST /work-sessions/start`,
  `POST /production-orders/<id>/start`.
- **Code currently does**: every business Blueprint in
  `app/mesflow/web/*.py` declares `url_prefix='/api'`
  (`analytics.py`, `execution.py`, `master_data.py`, `exceptions.py`,
  `trace.py`, `users.py`, `action_logging.py`, `system_health.py`,
  `excel_io.py` all confirmed) — the real, callable path always has
  `/api` prepended. Verified live: `curl .../reports/employee-productivity`
  -> `404 NOT_FOUND`; `curl .../api/reports/employee-productivity` ->
  `200`, real data.
- **Risk**: a QC agent generating tests directly from the master doc's
  literal path strings would 404 on every business API call — this is
  systemic, affecting essentially all ~161 distinct bare API path forms
  in Part B.
- **Recommended resolution / what was done**: added a correction notice
  to both `docs/MESFLOW_MASTER_REQUIREMENTS.md` and `_VI.md` (right
  after the "Requirement ID stability" paragraph, before Part A begins)
  stating the rule and its exceptions. Did NOT bulk-edit all ~161
  individual path mentions — the risk of a scripted find/replace
  silently corrupting prose (several bare forms like `/templates` or
  `/work-sessions` also appear in narrative text, not just as literal
  route paths) outweighed the benefit within this pass's scope. The
  QC package's own `docs/qc/API_MAP.yaml` and
  `docs/qc/MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md` use verified-correct
  paths throughout and should be the actual source for test generation
  (per `docs/qc/INDEX.md`'s reading order) — this closes the practical
  risk even though the master doc's raw text wasn't line-edited.

---

## GAP-002 — `/api/kiosk-events` referenced by the UI but does not exist

- **Requirement says**: not documented in the master requirement doc at
  all (this page id isn't in its §2 nav table).
- **Code currently does**: `app/mesflow/web/static/app.js`'s
  `openPage('kiosk-events')` branch calls
  `renderSimple('Kiosk Events', '/api/kiosk-events')`, but no route
  named exactly `/api/kiosk-events` exists anywhere in the 183-route
  inventory. The real kiosk event log route is `GET /api/kiosk/events`
  (slash, not hyphen, and singular `events` not `kiosk-events`).
- **Risk**: clicking into this reachable-but-not-nav-exposed page (see
  `docs/qc/APPLICATION_MAP.yaml` `reachable_but_not_nav_exposed`) would
  hit a 404 and render an empty/broken list — low real-world impact
  since it has no sidebar entry, but a UI test written against the
  wrong assumption would fail confusingly.
- **Recommended resolution**: not fixed in this pass (a UI-only string
  fix, out of the tutorial-pipeline bug-fix budget and not part of this
  audit's explicit scope). Flagged here so a QC agent doesn't assume
  this page id has a working data source; recommend a one-line source
  fix (`'/api/kiosk-events'` -> `'/api/kiosk/events'`) in a future pass
  with its own test evidence.

---

## GAP-003 — Several `/api/system-health/*` routes are not documented at all

- **Requirement says**: nothing — the master doc's System Console
  section only covers the 6 `super_admin`-gated routes (errors,
  services, service-restart, diagnostics, diagnostics-run, audit).
- **Code currently does**: `app/mesflow/web/system_health.py` has 13
  MORE routes under the same `/api/system-health` prefix that are
  `login_required` only (any authenticated role), not
  `super_admin_required`: per-alert AI-analysis (+regenerate), per-alert
  diagnostics, per-alert notifications, history, kiosks/kiosk-detail,
  logs, metric-trend, notification-channels (+test), predictions,
  recurring-incidents.
- **Risk**: a QC agent assuming "everything under `/api/system-health`
  is `super_admin`-only" (a reasonable inference from the master doc's
  framing) would write an incorrect RBAC test expecting a 403 that
  never happens — `docs/qc/API_MAP.yaml`'s `system_health_alerts` group
  and `QC-EXEC-HEALTH-001` in the executable requirements exist
  specifically to prevent this.
- **Recommended resolution**: not fixed (this is a documentation gap,
  not a code defect — no evidence either access level is "wrong"; may
  be intentional, e.g. any user can view predictive alerts for
  situational awareness while only `super_admin` can act on them via
  the 6 gated routes). Flagged as `docs/qc/FEATURE_MAP.yaml`'s
  `system_health_alerts` feature; a human product decision would be
  needed to say whether this is the intended access split.

---

## GAP-004 — `/api/reports/employee-performance` is undocumented and its relationship to `employee-productivity` is unclear

- **Requirement says**: nothing — only `employee-productivity` and its
  sub-routes are documented.
- **Code currently does**: `GET /api/reports/employee-performance`
  exists as a distinct, separately-routed endpoint
  (`app/mesflow/web/analytics.py`), `login_required`.
- **Risk**: a QC agent might assume this is a typo/duplicate of
  `employee-productivity` and skip it, or conversely assume feature
  parity it may not have.
- **Recommended resolution**: not resolved — genuinely unclear from
  routing alone whether this is a legacy/superseded endpoint, a
  differently-scoped report, or actively used. **OPEN-QUESTION**, not
  guessed at; see `docs/qc/API_MAP.yaml`'s note on this route.

---

## GAP-005 — `/api/production-control` vs. `/api/production-schedule` distinction unclear

- **Requirement says**: only `production-schedule` (Gantt & Material
  Flow) is documented.
- **Code currently does**: `GET /api/production-control` exists as a
  separate, `login_required` route (`app/mesflow/web/execution.py`).
- **Risk**: same class as GAP-004 — a QC agent could conflate or skip
  this feature incorrectly.
- **Recommended resolution**: not resolved — **OPEN-QUESTION**; flagged
  in `docs/qc/API_MAP.yaml` under `production_schedule`.

---

## GAP-006 — `/api/system/health` vs. `/api/system/ready` distinction unclear

- **Requirement says**: only `/api/system/ready` is documented (as the
  deploy-pipeline health contract, NFR-006/007).
- **Code currently does**: `GET /api/system/health` is a separate,
  unauthenticated route.
- **Risk**: a QC agent asserting deploy-pipeline behavior (NFR-006)
  against the wrong one of these two would produce a misleading result.
- **Recommended resolution**: not resolved — **OPEN-QUESTION**; likely a
  liveness-vs-readiness split (common pattern) but not confirmed against
  source in this pass. Flagged in `docs/qc/API_MAP.yaml`.

---

## GAP-007 — Generic RBAC-prefix carve-outs are real but only findable in code, not in the master doc's own §3.4 table

- **Requirement says**: §3.4 lists 4 "deliberate exceptions" (force-delete,
  PO start, templates/demo, export-workbook) as a curated, standalone
  table.
- **Code currently does**: those 4 exceptions exist as literal
  early-return carve-outs inside `_permission_for_request()` in
  `app/mesflow/web/auth.py`, confirmed byte-for-byte matching the
  master doc's table — **this is not actually a gap**, it's full
  agreement, called out here only because verifying it required reading
  a different mechanism (a generic prefix-mapper with explicit
  exclusions) than the doc's framing ("deliberate exceptions to the
  generic per-prefix rule") might suggest to a reader expecting a
  simple lookup table. No action needed; documented for traceability in
  `docs/qc/RBAC_MAP.yaml`'s `enforcement_rules.generic_prefix_mapping`.

---

## GAP-008 — `production-trace` and `employee-productivity` page mount via a monkey-patch chain, not app.js's own if-chain

- **Requirement says**: nothing — the master doc's §2 doesn't describe
  the page-dispatch mechanism at all (out of its own scope).
- **Code currently does**: `app/mesflow/web/static/pages/production-trace.js`
  and `employee-productivity.js` each capture the current global
  `openPage`, wrap it with their own id-check, and reassign the global —
  a working, deliberate pattern (confirmed via the files' own comments
  citing each other as precedent), not a bug. Initially misread as "no
  handler found" during this audit until the pattern was traced.
- **Risk**: none once known; a QC agent statically grepping only
  `app.js`'s own if-chain (as this audit initially did) would wrongly
  conclude these two pages are broken/unmounted.
- **Recommended resolution**: not a defect — documented in
  `docs/qc/APPLICATION_MAP.yaml`'s `shell.page_switch_function` note so
  a future audit doesn't repeat the same false-negative.

---

## Summary

| Gap | Type | Status |
|---|---|---|
| GAP-001 | Confirmed wrong, systemic | Corrected (erratum notice added to both master docs) |
| GAP-002 | Confirmed wrong, narrow (1 stale UI string) | Flagged, not fixed (out of scope budget) |
| GAP-003 | Undocumented code surface | Flagged, OPEN-QUESTION on intended access level |
| GAP-004 | Undocumented code surface | Flagged, OPEN-QUESTION |
| GAP-005 | Undocumented code surface | Flagged, OPEN-QUESTION |
| GAP-006 | Undocumented code surface | Flagged, OPEN-QUESTION |
| GAP-007 | False alarm, resolved as agreement | No action needed |
| GAP-008 | Audit methodology false-negative, resolved as agreement | No action needed |
