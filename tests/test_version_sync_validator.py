import subprocess
from pathlib import Path

# Issue #25 (2026-09-07): VERSION.txt/release.json drifted from compose.yml's
# fallback image tag for an extended period before anyone noticed -- the
# existing per-feature test files (test_v65844*.py etc) each duplicate the
# same 3-4 line release-contract assertion inline, with no shared, clearly
# labelled failure message pointing at the fix. This test instead runs the
# actual authoritative validator (scripts/check-version-sync.sh, also used
# standalone and by scripts/release-local-qa.sh) so a drift fails fast, in
# plain `pytest`, with the exact same VERSION_DRIFT/VERSION_CONTRACT message
# a human running the script directly would see -- and points at the one
# real fix (scripts/bump-version.sh --if-released), not a numeric patch.
ROOT = Path(__file__).resolve().parents[1]


def test_release_declarations_agree_with_version_txt():
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "check-version-sync.sh")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "Release-contract drift detected by scripts/check-version-sync.sh "
        "(VERSION.txt vs release.json/compose.yml/app/mesflow/__init__.py). "
        "Run `scripts/bump-version.sh --if-released` to resynchronize -- "
        "never hand-patch a version number in just one file.\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
