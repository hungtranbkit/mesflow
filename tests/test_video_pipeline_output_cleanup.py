"""Regression test for the 2026-09-05 "manifest says 15, publish sees 19
with duplicate slot numbers" incident.

Root cause, reproduced live: scripts/make-user-guide-video.sh always
wiped its scratch $WORKSPACE before a run, but never $OUT (where
recorded/voiced videos land) -- a stale run's files (observed: four
files from 2026-08-11, predating employeeProductivity's insertion at
slot 10, still using the old 10_working_calendar/11_users_permissions/
12_system_logs/13_common_cases numbering) sat there indefinitely and
got published alongside a correct fresh 15-file run.

Pure source-tree check, no Docker/Postgres/running app needed.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_cleans_output_dir_before_recording():
    text = (ROOT / "scripts" / "make-user-guide-video.sh").read_text(encoding="utf-8")
    # Must rm -rf $OUT (not just $WORKSPACE) before any video gets written,
    # so a stale prior run's files can never survive into a fresh one.
    m = re.search(r'^rm -rf ("\$WORKSPACE"[^\n]*)$', text, re.M)
    assert m, "expected an `rm -rf \"$WORKSPACE\" ...` cleanup line before the recording loop"
    assert '"$OUT"' in m.group(1), (
        "the cleanup line no longer clears $OUT -- this is exactly the regression "
        "that let 2026-08-11 leftovers get published alongside a 2026-09-05 run "
        "(see reports for that incident)"
    )
    # And it must happen before mkdir -p "$OUT" (i.e. before anything else
    # writes into it), not after.
    clean_pos = text.index(m.group(0))
    mkdir_pos = text.index('mkdir -p "$WORKSPACE')
    assert clean_pos < mkdir_pos, "$OUT must be cleaned before it is recreated/populated"
