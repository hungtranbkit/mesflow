"""Deterministic ESP Kiosk tutorial CI fixture (scripts/test/generate-
esp-tutorial-fixture.sh) -- fixes the real, previously-failing baseline:
tests/e2e/mesflow.spec.js's "ESP Kiosk tutorial loads seven runtime
videos and plays" expected #espTutorialVersions to contain "5.1.9.2" but
got an empty string on a fresh CI checkout, because the real device-
captured manifest/videos at runtime/tutorials/esp-kiosk/ are gitignored
(AGENTS.md rule 8) and only ever exist on a machine that happened to
already have a real capture sitting there.

Dockerfile.test's image is Python-only and does not carry ffmpeg -- the
real generation always runs on the CI runner/host directly, before any
container starts (scripts/test/docker-test.sh), which is exactly what
this test also exercises when ffmpeg is available locally, same
reasoning tests/test_employee_productivity_display_settings.py already
uses for its own node-on-PATH skip."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'test' / 'generate-esp-tutorial-fixture.sh'
MANIFEST = ROOT / 'runtime' / 'tutorials' / 'esp-kiosk' / 'manifest.json'
VIDEOS_DIR = ROOT / 'runtime' / 'tutorials' / 'esp-kiosk' / 'videos'

pytestmark = pytest.mark.skipif(
    shutil.which('ffmpeg') is None,
    reason="ffmpeg not on PATH in this test image -- the real generation always runs on the CI runner/host directly (scripts/test/docker-test.sh), before any container starts",
)


def test_docker_test_sh_generates_the_fixture_before_bringing_up_the_api():
    script = (ROOT / 'scripts' / 'test' / 'docker-test.sh').read_text()
    assert './scripts/test/generate-esp-tutorial-fixture.sh' in script
    generate_line = script.index('\n./scripts/test/generate-esp-tutorial-fixture.sh')
    up_line = script.index('compose.test.yml up --build -d postgres-test mesflow-test-api')
    assert generate_line < up_line


def test_generator_produces_a_manifest_matching_the_real_e2e_contract(tmp_path, monkeypatch):
    # Run against a disposable copy of the repo tree so this never
    # touches a real developer capture that might already be sitting in
    # THIS checkout's own runtime/ directory.
    work = tmp_path / 'repo'
    work.mkdir()
    (work / 'scripts' / 'test').mkdir(parents=True)
    shutil.copy(SCRIPT, work / 'scripts' / 'test' / SCRIPT.name)
    (work / 'scripts' / 'test' / SCRIPT.name).chmod(0o755)

    result = subprocess.run([str(work / 'scripts' / 'test' / SCRIPT.name)], cwd=work, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr

    manifest_path = work / 'runtime' / 'tutorials' / 'esp-kiosk' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['type'] == 'esp-kiosk-tutorial'
    assert manifest['tutorial_version'] == '5.1.9.2'  # exact string tests/e2e/mesflow.spec.js asserts
    assert len(manifest['videos']) == 7  # exact count tests/e2e/mesflow.spec.js asserts

    videos_dir = work / 'runtime' / 'tutorials' / 'esp-kiosk' / 'videos'
    filenames = {v['filename'] for v in manifest['videos']}
    assert len(filenames) == 7  # every filename distinct
    for v in manifest['videos']:
        assert v['title']  # non-empty -- rendered as #espTutorialPlayerTitle text
        f = videos_dir / v['filename']
        assert f.is_file()
        assert f.stat().st_size > 1000  # a real encoded video, not a stub/empty file

    orders = sorted(v['order'] for v in manifest['videos'])
    assert orders == list(range(7))


def test_generator_is_a_real_playable_mp4_not_a_stub(tmp_path):
    """Directly probes one generated file with ffprobe -- proves it is a
    real, decodable video (what the E2E test's `video.play()` /
    `currentTime > 0` assertions actually require), not just a file that
    happens to have the right extension."""
    work = tmp_path / 'repo'
    work.mkdir()
    (work / 'scripts' / 'test').mkdir(parents=True)
    shutil.copy(SCRIPT, work / 'scripts' / 'test' / SCRIPT.name)
    (work / 'scripts' / 'test' / SCRIPT.name).chmod(0o755)
    subprocess.run([str(work / 'scripts' / 'test' / SCRIPT.name)], cwd=work, text=True, capture_output=True, check=True)

    first_video = work / 'runtime' / 'tutorials' / 'esp-kiosk' / 'videos' / '00_kiosk_overview.mp4'
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name', '-of', 'json', str(first_video)],
        text=True, capture_output=True, check=True,
    )
    streams = json.loads(probe.stdout)['streams']
    assert any(s['codec_type'] == 'video' for s in streams)


def test_generator_never_overwrites_a_real_pre_existing_capture(tmp_path):
    """Section: 'no production runtime regression' -- a manifest.json
    that already exists and was NOT written by this generator (i.e. a
    real device capture, or anything a human placed there) must be left
    untouched, never silently clobbered."""
    work = tmp_path / 'repo'
    work.mkdir()
    (work / 'scripts' / 'test').mkdir(parents=True)
    shutil.copy(SCRIPT, work / 'scripts' / 'test' / SCRIPT.name)
    (work / 'scripts' / 'test' / SCRIPT.name).chmod(0o755)
    real_dir = work / 'runtime' / 'tutorials' / 'esp-kiosk'
    real_dir.mkdir(parents=True)
    real_manifest = {"type": "esp-kiosk-tutorial", "tutorial_version": "9.9.9", "generated_by": "a-real-capture-pipeline", "videos": []}
    (real_dir / 'manifest.json').write_text(json.dumps(real_manifest), encoding='utf-8')

    result = subprocess.run([str(work / 'scripts' / 'test' / SCRIPT.name)], cwd=work, text=True, capture_output=True)
    assert result.returncode == 0
    assert 'untouched' in (result.stdout + result.stderr)
    still_there = json.loads((real_dir / 'manifest.json').read_text(encoding='utf-8'))
    assert still_there == real_manifest
