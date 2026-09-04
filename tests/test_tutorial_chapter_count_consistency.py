"""Regression test for the 2026-09 "manifest says 15, UI/API shows 13/14"
incident (`reports/PRODTEST_TUTORIAL_VIDEO_FIX_20260904.md`).

Root cause that day was an infra gap (prodtest's compose.yml had no
volume mount for /data/tutorials at all), not a source-level defect --
but the task this test was written under ("fix triệt để... không chấp
nhận fix bằng hard-code count") asked for a regression test that would
catch any FUTURE drift between the four places a chapter must be
declared consistently, at the SOURCE level, before a single video is
ever generated or deployed:

  1. scripts/make-user-guide-video.sh's MODULES array (what the
     recording pipeline will actually generate)
  2. scripts/publish-user-guide-videos.sh's TITLES/CATS/DESCS + the
     `for key in ...` publish loop (what gets written into the served
     manifest.json)
  3. tutorial/narration/<id>.txt (voice-over source per chapter)
  4. tutorial/coverage-matrix.json's `features` list (QA coverage
     tracking -- one entry per chapter except the pure-intro 00_overview)

This deliberately does NOT touch a live server, container, or
generated video file -- it is a pure source-tree consistency check, so
it runs in plain `pytest` with no Docker/Postgres dependency and can't
be skipped/flaky in CI. The live post-publish count check (manifest
API == UI == physical file count) is a separate, environment-specific
verification step documented in the tutorial-video report, not
something a static test can assert once and for all across every
target environment.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _pipeline_module_entries() -> list[tuple[str, str]]:
    """Returns [(chapter_id, tour_module_name), ...] straight from the
    "NN_chapter_id:tourModuleName" entries in MODULES=(...)."""
    text = (ROOT / "scripts" / "make-user-guide-video.sh").read_text(encoding="utf-8")
    m = re.search(r"MODULES=\((.*?)\n\)", text, re.S)
    assert m, "MODULES array not found in make-user-guide-video.sh -- did its shape change?"
    out = []
    for line in m.group(1).splitlines():
        line = line.strip().strip('"')
        if not line:
            continue
        chapter_id, _, tour_module = line.partition(":")
        out.append((chapter_id, tour_module))
    return out


def _pipeline_module_ids() -> list[str]:
    return [chapter_id for chapter_id, _ in _pipeline_module_entries()]


def _publish_declared_ids() -> tuple[list[str], list[str]]:
    """Returns (ids with TITLES/CATS/DESCS entries, ids in the final publish loop)."""
    text = (ROOT / "scripts" / "publish-user-guide-videos.sh").read_text(encoding="utf-8")
    title_ids = re.findall(r"^TITLES\[(\w+)\]=", text, re.M)
    loop_m = re.search(r"^for key in ([0-9a-z_ ]+); do", text, re.M)
    assert loop_m, "publish loop ('for key in ...') not found in publish-user-guide-videos.sh"
    loop_ids = loop_m.group(1).split()
    return title_ids, loop_ids


def _narration_ids() -> list[str]:
    return sorted(p.stem for p in (ROOT / "tutorial" / "narration").glob("*.txt"))


def _coverage_matrix_modules() -> list[str]:
    import json
    data = json.loads((ROOT / "tutorial" / "coverage-matrix.json").read_text(encoding="utf-8"))
    return [f["module"] for f in data["features"]]


def test_pipeline_publish_and_narration_declare_the_same_chapter_set():
    """The exact class of bug this test exists for: a chapter renumbered/
    added/removed in ONE of these files but not the others -- e.g. the
    real historical case where narration files kept old numbers (10-13)
    after the pipeline and publish script had already moved to 11-14."""
    pipeline_ids = _pipeline_module_ids()
    title_ids, loop_ids = _publish_declared_ids()
    narration_ids = _narration_ids()

    assert len(pipeline_ids) == len(set(pipeline_ids)), "duplicate module id in MODULES array"
    assert set(pipeline_ids) == set(title_ids), (
        f"pipeline declares {sorted(set(pipeline_ids) - set(title_ids))} chapters "
        f"with no TITLES/CATS/DESCS entry in publish-user-guide-videos.sh, or vice versa: "
        f"{sorted(set(title_ids) - set(pipeline_ids))}"
    )
    assert set(pipeline_ids) == set(loop_ids), (
        f"pipeline/publish-loop mismatch: {sorted(set(pipeline_ids) ^ set(loop_ids))}"
    )
    assert set(pipeline_ids) == set(narration_ids), (
        f"pipeline/narration-file mismatch: {sorted(set(pipeline_ids) ^ set(narration_ids))} "
        f"-- every chapter in MODULES needs an exactly-matching tutorial/narration/<id>.txt"
    )


def test_chapter_count_is_exactly_fifteen():
    """Not a hard-coded "fix" -- a floor asserting the currently-spec'd
    chapter set size, so a future PR that silently drops a chapter (the
    other half of the historical incident: prodtest showing 13/14
    instead of the full set) fails CI instead of only being caught by a
    human eyeballing a screenshot."""
    pipeline_ids = _pipeline_module_ids()
    assert len(pipeline_ids) == 15, (
        f"Expected exactly 15 declared chapters (00-14), found {len(pipeline_ids)}: {pipeline_ids}. "
        f"If this is a deliberate spec change, update this test's expected count in the same PR "
        f"that changes MODULES -- never let the two drift independently."
    )
    assert pipeline_ids == sorted(pipeline_ids), "MODULES array is not in chapter-number order"
    assert pipeline_ids[0] == "00_overview" and pipeline_ids[-1] == "14_common_cases"


def test_employee_productivity_chapter_present_and_positioned():
    """Requirement-specific regression: the "Năng suất nhân viên" chapter
    (this system's own previously-missing coverage gap) must exist, and
    must sit between the Kiosk chapters and the system-settings chapters
    -- not accidentally reordered to the very end or dropped again."""
    pipeline_ids = _pipeline_module_ids()
    assert "10_employee_productivity" in pipeline_ids
    idx = pipeline_ids.index("10_employee_productivity")
    assert pipeline_ids[idx - 1] == "09_kiosk_operator"
    assert pipeline_ids[idx + 1] == "11_working_calendar"


def test_coverage_matrix_tracks_every_non_intro_chapter():
    """00_overview is the only chapter with no dedicated coverage-matrix
    feature entry (it's a pure introduction, not a feature) -- every
    other chapter's underlying tour module must be tracked for the QA
    coverage-threshold gate (tests/e2e/tutorial-coverage.spec.js).

    Joined on the tour MODULE name (MODULES=(...)'s "chapter:module"
    second half, e.g. "employeeProductivity"), which is the real shared
    key between the recording pipeline and coverage-matrix.json's own
    `module` field -- NOT the chapter id's text (several chapters'
    coverage-matrix feature id deliberately differs from their chapter
    id, e.g. chapter `12_users_permissions` tracks feature id
    `permissions`; `14_common_cases` maps to TWO features,
    `import_export` and `equipment`, both module `commonCases` -- id-only
    comparison would be a false positive here, not a real gap)."""
    pipeline_modules = {module for chapter_id, module in _pipeline_module_entries() if chapter_id != "00_overview"}
    covered_modules = set(_coverage_matrix_modules())
    missing = pipeline_modules - covered_modules
    assert not missing, (
        f"Chapters whose tour module has no coverage-matrix.json feature entry: {sorted(missing)} -- "
        f"every non-intro chapter needs QA coverage tracking, or the tutorial-coverage "
        f"gate's threshold math is silently computed over an incomplete feature set."
    )
