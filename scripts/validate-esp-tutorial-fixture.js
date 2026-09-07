#!/usr/bin/env node
// Preflight validator for the ESP Kiosk tutorial video fixture
// (MESFLOW_ESP_TUTORIAL_DIR / compose's /data/tutorials/esp-kiosk).
//
// Root cause this exists for (found 2026-09-07, real live evidence):
// /opt/mesflow/runtime/tutorials/esp-kiosk on the shared DEV deployment,
// and compose.sandbox.yml's `app` service (used by every ProjectFlow
// Workspace Manager ephemeral sandbox), never mount/seed this directory at
// all. The app itself degrades this gracefully (GET /api/esp-kiosk-tutorial
// returns `{ok:true,manifest:null}` and the UI shows an honest empty
// state) -- so a missing fixture does not crash anything, it just makes
// `tests/e2e/mesflow.spec.js`'s "ESP Kiosk tutorial loads seven runtime
// videos and plays" test fail with a confusing assertion deep inside the
// test (`expect(...#espTutorialList button).toHaveCount(7)` etc), which is
// indistinguishable at a glance from a real app regression.
//
// This turns that into an immediate, specific, un-skippable ENV/DATA
// error before Playwright even starts, or (with --seed) regenerates a
// known-good synthetic fixture via the project's existing generator,
// scripts/test/generate-esp-tutorial-fixture.sh (real, browser-playable
// ffmpeg-synthesized MP4s -- never the real device-captured videos, which
// are deliberately gitignored per AGENTS.md rule 8 and must not be
// committed).
//
// Usage:
//   node scripts/validate-esp-tutorial-fixture.js [--dir <path>] [--seed]
//
//   --dir <path>  Directory to validate (default: env
//                 MESFLOW_ESP_TUTORIAL_FIXTURE_DIR, else
//                 "runtime/tutorials/esp-kiosk" relative to repo root).
//   --seed        If the target is missing/invalid, run
//                 scripts/test/generate-esp-tutorial-fixture.sh (only
//                 supports the default runtime/tutorials/esp-kiosk path --
//                 that script never clobbers a real, already-published
//                 manifest, see its own header), then re-validate.
//
// Exit code 0 = fixture present and structurally valid. Exit code 1 = a
// specific, printed reason why it is not -- never a silent pass.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..');
const DEFAULT_DIR = path.join(REPO_ROOT, 'runtime', 'tutorials', 'esp-kiosk');
const GENERATOR = path.join(REPO_ROOT, 'scripts', 'test', 'generate-esp-tutorial-fixture.sh');

function parseArgs(argv) {
  const out = { dir: null, seed: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--dir') { out.dir = argv[++i]; }
    else if (argv[i] === '--seed') { out.seed = true; }
  }
  return out;
}

function fail(reason) {
  console.error('[esp-tutorial-fixture] MISSING/INVALID: ' + reason);
  console.error('[esp-tutorial-fixture] classification: DATA_ISSUE / ENV_INFRA_ISSUE (not an app bug).');
  console.error('[esp-tutorial-fixture] fix: node scripts/validate-esp-tutorial-fixture.js --seed');
  console.error('  (regenerates a synthetic fixture via scripts/test/generate-esp-tutorial-fixture.sh,');
  console.error('   or mount a real published esp-kiosk tutorial at the target path.)');
  process.exit(1);
}

function validate(targetDir) {
  const manifestPath = path.join(targetDir, 'manifest.json');
  if (!fs.existsSync(targetDir)) return { ok: false, reason: `directory does not exist: ${targetDir}` };
  if (!fs.existsSync(manifestPath)) return { ok: false, reason: `manifest.json not found at ${manifestPath} -- ESP Kiosk tutorial fixture was never mounted/seeded into this environment.` };

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch (ex) {
    return { ok: false, reason: `manifest.json is not valid JSON: ${ex.message}` };
  }
  if (manifest.type !== 'esp-kiosk-tutorial') return { ok: false, reason: `manifest.json has type=${JSON.stringify(manifest.type)}, expected "esp-kiosk-tutorial"` };
  if (!Array.isArray(manifest.videos) || manifest.videos.length === 0) return { ok: false, reason: 'manifest.json has no videos[] entries' };

  const missing = [];
  const empty = [];
  for (const video of manifest.videos) {
    const filename = video && video.filename;
    if (!filename) { missing.push('(entry with no filename)'); continue; }
    const videoPath = path.join(targetDir, 'videos', filename);
    if (!fs.existsSync(videoPath)) { missing.push(filename); continue; }
    if (fs.statSync(videoPath).size === 0) { empty.push(filename); }
  }
  if (missing.length) return { ok: false, reason: `${missing.length} video file(s) listed in manifest.json are missing on disk: ${missing.join(', ')}` };
  if (empty.length) return { ok: false, reason: `${empty.length} video file(s) are present but zero bytes: ${empty.join(', ')}` };

  return { ok: true, manifest };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const targetDir = path.resolve(args.dir || process.env.MESFLOW_ESP_TUTORIAL_FIXTURE_DIR || DEFAULT_DIR);

  let result = validate(targetDir);

  if (!result.ok && args.seed) {
    if (targetDir !== DEFAULT_DIR) {
      fail(`${result.reason}\n[esp-tutorial-fixture] --seed only supports the default path (${DEFAULT_DIR}); ` +
        `the generator writes there. Point --dir there, or seed manually and re-run without --seed to just validate.`);
    }
    if (!fs.existsSync(GENERATOR)) {
      fail(`${result.reason}\n[esp-tutorial-fixture] --seed requested but generator script is missing: ${GENERATOR}`);
    }
    console.log(`[esp-tutorial-fixture] ${result.reason} -- running ${path.relative(REPO_ROOT, GENERATOR)} to seed a synthetic fixture.`);
    const proc = spawnSync(GENERATOR, [], { cwd: REPO_ROOT, stdio: 'inherit' });
    if (proc.status !== 0) {
      fail(`generator script exited with status ${proc.status}${proc.error ? ' (' + proc.error.message + ')' : ''}`);
    }
    result = validate(targetDir);
  }

  if (!result.ok) fail(result.reason);

  console.log(`[esp-tutorial-fixture] OK: ${targetDir} — tutorial_version=${result.manifest.tutorial_version}, ${result.manifest.videos.length} video(s) present and non-empty.`);
  process.exit(0);
}

main();
