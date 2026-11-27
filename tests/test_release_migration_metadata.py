"""Run the canonical packager with a fake Docker boundary; inspect its ZIP."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISSING = object()


@pytest.fixture()
def package_release(tmp_path):
    source = tmp_path / 'source'
    scripts = source / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/build-release.sh', scripts / 'build-release.sh')
    (source / 'VERSION.txt').write_text('1.2.3.4\n')
    (source / 'compose.yml').write_text('services: {}\n')
    migrations = source / 'app/migrations/versions'
    migrations.mkdir(parents=True)
    (migrations / 'fixture.py').write_text("revision='fixture_schema'\ndown_revision=None\n")
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    docker_log = tmp_path / 'docker-calls.jsonl'
    docker = binaries / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
with pathlib.Path(os.environ['MESFLOW_TEST_DOCKER_LOG']).open('a') as log:
    log.write(json.dumps(args)+'\\n')
if args[:2]==['image','inspect']:
    if '__building_' not in args[2]: sys.exit(1)
    print('sha256:'+'a'*64)
elif args[0]=='save':
    pathlib.Path(args[args.index('-o')+1]).write_bytes(b'fixture-image-archive')
elif args[0] not in ('build','tag','rmi'):
    raise RuntimeError('unexpected Docker boundary call')
''')
    docker.chmod(0o755)
    git = binaries / 'git'
    git.write_text('''#!/usr/bin/env python3
import sys
if '--git-common-dir' in sys.argv: sys.exit(1)
if 'rev-parse' not in sys.argv: raise RuntimeError('unexpected Git boundary call')
print('b'*40)
''')
    git.chmod(0o755)
    env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
           'MESFLOW_TEST_DOCKER_LOG': str(docker_log), 'MESFLOW_IMAGE_REPOSITORY': 'fixture-mesflow'}

    def run(flag=MISSING, raw=None):
        metadata = {'version': '1.2.3.4'}
        if flag is not MISSING:
            metadata['requires_migration'] = flag
        (source / 'release.json').write_text(json.dumps(metadata) if raw is None else raw)
        process = subprocess.run(['bash', str(scripts / 'build-release.sh')], cwd=source,
                                 env=env, capture_output=True, text=True, timeout=20)
        artifact = tmp_path / 'artifacts/releases/1.2.3.4'
        calls = [json.loads(line) for line in docker_log.read_text().splitlines()] if docker_log.exists() else []
        return process, artifact, calls

    return run


@pytest.mark.parametrize(('flag', 'expected'), [(True, True), (False, False), (MISSING, False)])
def test_manifest_preserves_declared_migration_boolean(package_release, flag, expected):
    process, artifact, calls = package_release(flag)
    assert process.returncode == 0, process.stderr
    manifest = json.loads((artifact / 'release.json').read_text())
    assert manifest['requires_migration'] is expected
    assert manifest['schema_revision'] == 'fixture_schema'
    assert sum(call[0] == 'build' for call in calls) == 1
    with zipfile.ZipFile(artifact / 'MESFlow_1.2.3.4.deploy.zip') as bundle:
        raw = bundle.read('mesflow-release/release.json')
        assert json.loads(raw) == manifest
        checksums = bundle.read('mesflow-release/checksums.txt').decode()
        assert hashlib.sha256(raw).hexdigest() + '  release.json' in checksums


@pytest.mark.parametrize('invalid', [None, 'true', 'false', 1, 0, [], {}])
def test_invalid_migration_metadata_stops_before_build_or_version_directory(package_release, invalid):
    process, artifact, calls = package_release(invalid)
    assert process.returncode != 0
    assert not artifact.exists()
    assert calls == []


@pytest.mark.parametrize('raw', ['{broken-json', '[]'])
def test_malformed_source_metadata_stops_before_build(package_release, raw):
    process, artifact, calls = package_release(raw=raw)
    assert process.returncode != 0
    assert not artifact.exists()
    assert calls == []
