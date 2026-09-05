#!/usr/bin/env python3
"""Dry-run test-generation report from the QC package. Does NOT execute
any test — it parses docs/qc/MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md and
reports how many tests WOULD be generated, broken down by executor, plus
anything that would be blocked/skipped and why. Safe to run against any
checkout; makes no network/DB calls.
"""
import re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
QC_DIR = ROOT / "docs" / "qc"

exec_req_text = (QC_DIR / "MESFLOW_QC_EXECUTABLE_REQUIREMENTS.md").read_text(encoding="utf-8")
classification = (QC_DIR / "REQUIREMENT_CLASSIFICATION.yaml").read_text(encoding="utf-8")

# Strip the trailing "## Coverage summary" section (not a requirement
# block) before splitting, so its own prose doesn't get parsed as part
# of the last real REQ block.
exec_req_text = exec_req_text.split("\n## Coverage summary")[0]

blocks = re.split(r"^### ", exec_req_text, flags=re.M)[1:]

executor_counts = Counter()
blocked_missing_account = []
blocked_missing_test_data = []
blocked_unknown_mapping = []
generated = []

for block in blocks:
    req_id = re.match(r"([\w-]+)", block).group(1)
    executor_m = re.search(r"\*\*Executor\*\*:\s*(.+)", block)
    executor = executor_m.group(1).strip() if executor_m else "unknown"
    feature_m = re.search(r"\*\*Feature\*\*:\s*(\S+)", block)
    feature = feature_m.group(1) if feature_m else None

    if "BLOCKED_missing_account" in block:
        blocked_missing_account.append(req_id)
        continue
    if "BLOCKED_missing_test_data" in block:
        blocked_missing_test_data.append(req_id)
        continue
    if feature is None:
        blocked_unknown_mapping.append(req_id)
        continue

    generated.append((req_id, executor))
    # classify primary executor bucket
    exec_lower = executor.lower()
    if "ui" in exec_lower and "api" not in exec_lower.split("+")[0]:
        pass
    if exec_lower.startswith("ui") or "+ ui" in exec_lower or exec_lower == "ui":
        executor_counts["ui"] += 1
    if exec_lower.startswith("api") or "api" in exec_lower:
        executor_counts["api"] += 1
    if "background_job" in exec_lower or "background job" in exec_lower:
        executor_counts["background_job"] += 1
    if "deterministic" in exec_lower:
        executor_counts["deterministic"] += 1
    if "db_read_readonly" in exec_lower or "db read" in exec_lower:
        executor_counts["db_read_readonly (paired oracle, not a standalone bucket)"] += 1

# Count classification sections excluded from generation
excluded_sections = re.findall(r'"(§[\d./]+.*?)"', classification.split("sections_absolutely_excluded_from_test_generation:")[1]) \
    if "sections_absolutely_excluded_from_test_generation:" in classification else []
excluded_count = classification.split("sections_absolutely_excluded_from_test_generation:")[1].count("- \"")

total = len(blocks)

print("=== MESFlow QC package — test-generation dry run ===")
print(f"Total executable requirement blocks parsed: {total}")
print(f"Generated (would produce a real test): {len(generated)}")
print(f"  - executor mentions 'ui':                 {executor_counts['ui']}")
print(f"  - executor mentions 'api':                {executor_counts['api']}")
print(f"  - executor mentions 'background_job':     {executor_counts['background_job']}")
print(f"  - executor mentions 'deterministic':      {executor_counts['deterministic']}")
print(f"  - paired with db_read_readonly oracle:    {executor_counts['db_read_readonly (paired oracle, not a standalone bucket)']}")
print(f"Skipped documentation sections (master doc, META/GLOSSARY/DESCRIPTION"
      f" classified — see REQUIREMENT_CLASSIFICATION.yaml): {excluded_count}")
print(f"Blocked — missing account: {len(blocked_missing_account)} {blocked_missing_account}")
print(f"Blocked — missing test data: {len(blocked_missing_test_data)} {blocked_missing_test_data}")
print(f"Blocked — unknown mapping (no Feature resolved): {len(blocked_unknown_mapping)} {blocked_unknown_mapping}")
print()
print("This is a DRY RUN — no test was executed, no target was contacted.")
