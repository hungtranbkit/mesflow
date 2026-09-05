# MESFlow QC Package — Reading Order

A QC/QA agent working on MESFlow should read these files **in this
order**. The master requirement docs
(`docs/MESFLOW_MASTER_REQUIREMENTS.md` / `_VI.md`) are **reference
material**, not the first thing to read — start here instead.

1. **`QC_PROJECT.yaml`** (repo root) — project/runtime/repository/auth
   summary, and pointers to everything else. Always start here.
2. **`APPLICATION_MAP.yaml`** — the admin app is a 30-view single-page
   app, not one screen. Understand the real page/view structure before
   anything else, so a "feature" in the next file maps to something real.
3. **`FEATURE_MAP.yaml`** — the 38-feature catalog every other file
   references by id.
4. **`RBAC_MAP.yaml`** — roles, permissions, and the 4 explicit
   carve-outs where the generic permission rule does NOT apply.
5. **`STATE_MACHINES.yaml`** — every entity with a real lifecycle:
   Work Session, Operation, Production Order, Exception Record,
   Kiosk v2 device.
6. **`API_MAP.yaml`** — all 183 routes, grouped by feature, with roles
   and surface (ui/api_only/device/background).
7. **`BUSINESS_RULES.yaml`** — atomic, verifiable rules (BR-*/NFR-*/QC-*),
   the 7 exception-detection conditions, the productivity formula.
8. **`EXECUTOR_MAP.yaml`** — how to actually drive each feature
   (ui/api/background_job/deterministic) — not everything belongs in a
   browser.
9. **`TEST_DATA.yaml`** — entity prerequisites, the existing TUT-
   tutorial-data factory, and the QC_TEST_ prefix convention for
   QC-owned fixtures.
10. **`ORACLES.yaml`** — how to decide PASS/FAIL per feature; a UI toast
    alone is never sufficient for anything that persists state.
11. **`SAFETY.yaml`** — what class a target is (local_dev / demo /
    prodtest / production) and what's permitted on each. Read before
    running ANY action, not just once.
12. **`MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md`** — the curated,
    directly-test-generatable requirement set. Generate tests from
    THIS file.

## Supporting files (consult as needed, not part of the linear read)

- **`REQUIREMENT_CLASSIFICATION.yaml`** — which sections of the master
  requirement docs are (and are not) source material for test generation.
- **`REQUIREMENT_CODE_GAPS.md`** — confirmed mismatches between the
  master requirement doc and the real running code, found during this
  audit.
- **`BACKGROUND_JOBS.yaml`** — the 3 real cron jobs (exception
  reconciliation, shift auto-close, log retention) plus manual-only
  diagnostic commands.
- **`TEST_ACCOUNTS.yaml`** — persona/role schema for test sessions (no
  real passwords).

## Validating the package

Run `python3 scripts/validate_qc_package.py` after editing anything under
`docs/qc/` — it must exit 0. It checks: every YAML file parses, REQ/feature
ids are unique, cross-references resolve (a feature id used in
API_MAP/EXECUTOR_MAP/BUSINESS_RULES/the executable-requirements file
must exist in FEATURE_MAP), every role referenced exists in the 6-role
set, every RBAC_MAP state-machine transition names a state that's
actually declared, every executable requirement has a non-empty Expected
Result, no META/GLOSSARY-classified section is marked
`generate_testcase: true`, and every real API route in
`app/mesflow/web/*.py` appears somewhere in `API_MAP.yaml`.

## What the master requirement docs are still for

`docs/MESFLOW_MASTER_REQUIREMENTS.md` (English) and
`MESFLOW_MASTER_REQUIREMENTS_VI.md` (Vietnamese) remain the authoritative
source for **exact wording**: precise error messages, precise formulas,
precise field names, sample data values, and the full SPEC-GAP/
OPEN-QUESTION list. When a file in this package says "see master doc
§N," that's where the verbatim detail lives — this package is the
structured index into it, not a replacement for it.
