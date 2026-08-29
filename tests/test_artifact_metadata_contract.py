"""PROJECT.yaml declares artifacts.metadata = ../artifacts/latest/mesflow-app.json
as the one machine-readable artifact metadata file external tooling (right
now: ProjectFlow Workspace Manager's DeploymentService) reads after a
build. scripts/build-release.sh must actually write that exact path, with
the full field set that contract's readers depend on -- a real bug this
guards against: the file simply didn't exist before, so any reader got a
silent None back instead of real artifact identity.

A real `docker build` is too slow for this suite (see build-release.sh's
own module comment / AGENTS.md on CI scope), so this follows the same
lightweight, static-content convention as test_release_contract_v6584433.py
and test_default_admin_password.py -- assert on the script's own source
and on PROJECT.yaml, not by actually invoking it."""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "build-release.sh").read_text(encoding="utf-8")

REQUIRED_METADATA_FIELDS = [
    "source_commit", "version", "image_name", "image_tag",
    "image_digest", "package_filename", "package_sha256", "built_at",
]


def test_project_yaml_artifacts_metadata_points_at_a_path_the_script_writes():
    # PROJECT.yaml is a ProjectFlow-only concern -- Dockerfile.test's own
    # COPY list deliberately doesn't ship it into the test image (same
    # idiom as this file's other "not available in this image" skips), so
    # this half of the check only runs on a real host checkout.
    project_yaml_path = ROOT / "PROJECT.yaml"
    if not project_yaml_path.is_file():
        pytest.skip("PROJECT.yaml not present in this test image -- run from a real checkout")
    # No PyYAML dependency in this repo's requirements -- match the exact
    # scalar line rather than pulling in a parser just for this assert.
    project_yaml = project_yaml_path.read_text(encoding="utf-8")
    m = re.search(r"^\s*metadata:\s*(\S+)\s*$", project_yaml, re.MULTILINE)
    assert m, "PROJECT.yaml has no artifacts.metadata entry"
    assert m.group(1) == "../artifacts/latest/mesflow-app.json"
    # The script must write to exactly this path (relative to $ROOT, which
    # is the repo root at runtime) -- not a similarly-named but different
    # location that would leave the declared contract unfulfilled again.
    assert '"$ROOT/../artifacts/latest/mesflow-app.json"' in SCRIPT


def test_build_script_writes_full_metadata_contract():
    # Every field ProjectFlow's DeploymentService is documented to persist
    # must actually be present in the JSON the script emits.
    metadata_block = re.search(r'metadata_json="\$\(printf \'(\{.*?\})\\n\'', SCRIPT, re.DOTALL)
    assert metadata_block, "no metadata_json printf template found in build-release.sh"
    template = metadata_block.group(1)
    for field in REQUIRED_METADATA_FIELDS:
        assert f'"{field}":' in template, f"missing field in artifact metadata contract: {field}"


def test_versioned_and_latest_metadata_are_written_from_the_same_variable():
    # Two files, one source of truth -- both writes must come from the
    # same $metadata_json value so they can never silently diverge.
    assert SCRIPT.count('printf \'%s\' "$metadata_json"') == 2


def test_versioned_release_metadata_is_never_overwritten_by_a_later_build():
    # The existing immutable-release guard (VERSION_ALREADY_RELEASED) must
    # still gate the whole release-artifact section, including the new
    # metadata write -- a later build must die before ever reaching it.
    guard_pos = SCRIPT.index("VERSION_ALREADY_RELEASED")
    metadata_pos = SCRIPT.index('printf \'%s\' "$metadata_json" > "$dist/image-info.json"')
    assert guard_pos < metadata_pos
