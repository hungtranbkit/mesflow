from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
def test_release():
 assert (R/"VERSION.txt").read_text().strip()=="65.8.44.36"
 assert json.loads((R/"release.json").read_text())["version"]=="65.8.44.36"
 assert "image: mesflow-app:65.8.44.36" in (R/"compose.yml").read_text()
def test_pacing_all_entrypoints():
 for rel in ["scripts/make-user-guide-video.sh","scripts/make-one-user-guide-video.sh"]:
  s=(R/rel).read_text()
  for v in ["6000","7500","10000"]: assert f":-{v}" in s
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 for v in ["6000","7500","10000"]: assert f"|| {v}" in s
def test_timeout_fix_preserved():
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 assert "scrollIntoViewIfNeeded" not in s[s.index("async function note"):s.index("async function login")]
 assert "target.scrollIntoView" in s
def test_batch_retry_preserved():
 s=(R/"scripts/make-user-guide-video.sh").read_text()
 assert "Retrying once with fresh browser" in s
 assert "FAILED=()" in s
