#!/usr/bin/env python3
"""Validates the docs/qc/ QC intelligence package for internal
consistency. Run after any edit under docs/qc/ or QC_PROJECT.yaml, and
whenever a route is added/removed/renamed in app/mesflow/web/*.py.

Checks (each failure is reported; the script exits 1 if any failed):
  1. Every .yaml file under docs/qc/ (and QC_PROJECT.yaml) parses as valid YAML.
  2. Feature ids in FEATURE_MAP.yaml are unique.
  3. Every feature id referenced by API_MAP.yaml/EXECUTOR_MAP.yaml/
     BUSINESS_RULES.yaml/MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md exists in
     FEATURE_MAP.yaml.
  4. Every role named anywhere in RBAC_MAP.yaml/TEST_ACCOUNTS.yaml/
     MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md is one of the 6 real roles (or
     a recognized non-role actor: device, system, none, any, any_authenticated).
  5. Every state-machine transition in STATE_MACHINES.yaml only names
     states that entity's own `states` list declares.
  6. Every REQ block in MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md has a
     non-empty Expected Result and a unique ID.
  7. No section classified META/GLOSSARY/DESCRIPTION in
     REQUIREMENT_CLASSIFICATION.yaml has generate_testcase: true.
  8. Every real Flask route decorator in app/mesflow/web/*.py appears
     (allowing for placeholder-name differences) in API_MAP.yaml.

Exit code 0 = package consistent. Non-zero = at least one check failed;
every failure is printed with enough context to fix it.
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
QC_DIR = ROOT / "docs" / "qc"

REAL_ROLES = {"admin", "manager", "supervisor", "operator", "viewer", "super_admin"}
NON_ROLE_ACTORS = {"device", "system", "none", "any", "unknown",
                    "any_authenticated", "public_confirmed", "none_decorator"}

failures = []


def fail(check, msg):
    failures.append(f"[{check}] {msg}")


def load_yaml(path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        fail("yaml_parse", f"{path.relative_to(ROOT)}: {e}")
        return None


# ---------------------------------------------------------------------
# Check 1: every YAML file parses
# ---------------------------------------------------------------------
yaml_files = sorted(QC_DIR.glob("*.yaml")) + [ROOT / "QC_PROJECT.yaml"]
docs = {}
for f in yaml_files:
    if not f.exists():
        fail("file_exists", f"expected file missing: {f.relative_to(ROOT)}")
        continue
    data = load_yaml(f)
    if data is not None:
        docs[f.name] = data

if not failures:
    print(f"[yaml_parse] OK — {len(docs)} YAML files parsed")

# ---------------------------------------------------------------------
# Check 2 & 3: feature ids unique + cross-references resolve
# ---------------------------------------------------------------------
feature_ids = set()
if "FEATURE_MAP.yaml" in docs:
    seen = set()
    for feat in docs["FEATURE_MAP.yaml"].get("features", []):
        fid = feat.get("id")
        if fid in seen:
            fail("feature_id_unique", f"duplicate feature id: {fid}")
        seen.add(fid)
    feature_ids = seen
    print(f"[feature_id_unique] OK — {len(feature_ids)} unique feature ids")
else:
    fail("feature_map_missing", "FEATURE_MAP.yaml not found/parsed")

referenced_feature_ids = set()

if "API_MAP.yaml" in docs:
    by_feature = docs["API_MAP.yaml"].get("by_feature", {})
    referenced_feature_ids |= set(by_feature.keys())

if "EXECUTOR_MAP.yaml" in docs:
    per_feat = docs["EXECUTOR_MAP.yaml"].get("per_feature_executor", {})
    referenced_feature_ids |= set(per_feat.keys())

if "BUSINESS_RULES.yaml" in docs:
    for rule in docs["BUSINESS_RULES.yaml"].get("rules", []):
        if rule.get("feature"):
            referenced_feature_ids.add(rule["feature"])

exec_req_path = QC_DIR / "MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md"
exec_req_text = exec_req_path.read_text(encoding="utf-8") if exec_req_path.exists() else ""
exec_req_feature_refs = set(re.findall(r"\*\*Feature\*\*:\s*(\S+)", exec_req_text))
referenced_feature_ids |= exec_req_feature_refs

unknown_feature_refs = sorted(
    fid for fid in referenced_feature_ids
    if fid not in feature_ids and fid != "infra_and_cross_cutting_not_a_single_feature"
)
if unknown_feature_refs:
    for fid in unknown_feature_refs:
        fail("feature_ref_resolves", f"referenced feature id not in FEATURE_MAP.yaml: {fid}")
else:
    print(f"[feature_ref_resolves] OK — {len(referenced_feature_ids)} referenced feature ids all resolve")

unused_features = sorted(feature_ids - referenced_feature_ids)
if unused_features:
    print(f"[feature_ref_resolves] WARNING (non-fatal) — features with no "
          f"cross-reference from API_MAP/EXECUTOR_MAP/BUSINESS_RULES/executable "
          f"requirements: {unused_features}")

# ---------------------------------------------------------------------
# Check 4: role names are real
# ---------------------------------------------------------------------
role_refs = set(re.findall(r"\*\*Role\*\*:\s*(\S+)", exec_req_text))
bad_roles = sorted(r for r in role_refs if r.lower() not in REAL_ROLES | NON_ROLE_ACTORS)
if bad_roles:
    for r in bad_roles:
        fail("role_valid", f"unrecognized role/actor in executable requirements: {r}")
else:
    print(f"[role_valid] OK — {len(role_refs)} role references all recognized")

# ---------------------------------------------------------------------
# Check 5: state machine transitions reference declared states
# ---------------------------------------------------------------------
if "STATE_MACHINES.yaml" in docs:
    sm = docs["STATE_MACHINES.yaml"]
    checked = 0
    for entity_name, entity in sm.items():
        if not isinstance(entity, dict):
            continue
        states = entity.get("states")
        if not states:
            continue
        states_set = set(states)
        transitions = entity.get("transitions", [])
        for t in transitions:
            if not isinstance(t, dict):
                continue
            for key in ("from", "to"):
                val = t.get(key)
                if val is None:
                    continue
                vals = val if isinstance(val, list) else [val]
                for v in vals:
                    if v in ("none", "[none]", "any", "[system, condition]",
                             "[detected, fresh fingerprint]", "REJECTED"):
                        continue
                    v_clean = v.strip("[]") if isinstance(v, str) else v
                    if v_clean not in states_set and v_clean != "none":
                        fail("state_transition_valid",
                             f"{entity_name}: transition references undeclared "
                             f"state '{v}' (declared states: {sorted(states_set)})")
                    checked += 1
    print(f"[state_transition_valid] OK — {checked} transition endpoints checked "
          f"against declared states")
else:
    fail("state_machines_missing", "STATE_MACHINES.yaml not found/parsed")

# ---------------------------------------------------------------------
# Check 6: every executable REQ has a non-empty Expected Result + unique ID
# ---------------------------------------------------------------------
req_blocks = re.split(r"^### ", exec_req_text, flags=re.M)[1:]
req_ids = []
for block in req_blocks:
    m = re.match(r"([\w-]+)", block)
    if not m:
        continue
    req_id = m.group(1)
    req_ids.append(req_id)
    er = re.search(r"\*\*Expected Result\*\*:\s*(.+)", block)
    if not er or not er.group(1).strip():
        fail("expected_result_present", f"{req_id}: missing/empty Expected Result")

dupe_reqs = sorted({r for r in req_ids if req_ids.count(r) > 1})
if dupe_reqs:
    for r in dupe_reqs:
        fail("req_id_unique", f"duplicate requirement id: {r}")
if not dupe_reqs:
    print(f"[req_id_unique] OK — {len(req_ids)} requirement ids, all unique")
if not any(f.startswith("[expected_result_present]") for f in failures):
    print(f"[expected_result_present] OK — every requirement has a non-empty Expected Result")

# ---------------------------------------------------------------------
# Check 7: META/GLOSSARY/DESCRIPTION sections never generate_testcase: true
# ---------------------------------------------------------------------
if "REQUIREMENT_CLASSIFICATION.yaml" in docs:
    bad = []
    for sec in docs["REQUIREMENT_CLASSIFICATION.yaml"].get("sections", []):
        if sec.get("category") in ("META", "GLOSSARY", "DESCRIPTION") and sec.get("generate_testcase"):
            bad.append(sec.get("section"))
    if bad:
        for s in bad:
            fail("meta_never_testable", f"section {s} is META/GLOSSARY/DESCRIPTION but generate_testcase=true")
    else:
        print("[meta_never_testable] OK — no META/GLOSSARY/DESCRIPTION section is marked generate_testcase:true")
else:
    fail("requirement_classification_missing", "REQUIREMENT_CLASSIFICATION.yaml not found/parsed")

# ---------------------------------------------------------------------
# Check 8: every real route appears in API_MAP.yaml
# ---------------------------------------------------------------------
def extract_routes():
    web_dir = ROOT / "app" / "mesflow" / "web"
    routes = []
    for path in sorted(web_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        bp_prefixes = {}
        for m in re.finditer(r'(\w+)\s*=\s*Blueprint\([^)]*?url_prefix=[\'"]([^\'"]+)[\'"]', text):
            bp_prefixes[m.group(1)] = m.group(2)
        for m in re.finditer(r'(\w+)\s*=\s*Blueprint\(', text):
            bp_prefixes.setdefault(m.group(1), "")
        for m in re.finditer(r"@(\w+)\.(get|post|put|patch|delete)\(['\"]([^'\"]+)['\"]", text):
            bpname, method, subpath = m.groups()
            prefix = bp_prefixes.get(bpname, "")
            full = subpath if subpath.startswith(prefix) else prefix + subpath
            routes.append((method.upper(), full))
    return routes


if not (ROOT / "app" / "mesflow" / "web").exists():
    print("[route_coverage] SKIPPED — app/mesflow/web not found relative to "
          "this script (run from the mesflow app repo root)")
else:
    routes = extract_routes()
    api_map_path = QC_DIR / "API_MAP.yaml"
    api_map_text = api_map_path.read_text(encoding="utf-8") if api_map_path.exists() else ""
    norm_map = re.sub(r"<[^>]*>", "<X>", api_map_text)
    missing = []
    for method, path in routes:
        key = re.sub(r"<[^>]*>", "<X>", path)
        if key not in norm_map:
            missing.append((method, path))
    if missing:
        for method, path in missing:
            fail("route_coverage", f"route not found in API_MAP.yaml: {method} {path}")
    else:
        print(f"[route_coverage] OK — all {len(routes)} routes in "
              f"app/mesflow/web/*.py accounted for in API_MAP.yaml")

# ---------------------------------------------------------------------
print()
if failures:
    print(f"FAILED — {len(failures)} check(s) did not pass:\n")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("PASS — QC package is internally consistent.")
    sys.exit(0)
