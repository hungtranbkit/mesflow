from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()
def test_version():
 assert (R/"VERSION.txt").read_text().strip()==E
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==E  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
 assert json.loads((R/"release.json").read_text())["version"]==E
def test_tutorial_mode():
 s=(R/"app/mesflow/web/static/kiosk.js").read_text()
 assert "get('tutorial') === '1'" in s
 assert "12000" in s and "9000" in s
def test_all_kiosk_screens_are_walked():
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 b=s[s.index("kioskUser: async page=>"):s.index("calendar: async page=>")]
 for x in ["#demo-toggle","#demo-scan-operation","#demo-scan-employee","#screen-error","#screen-operation","#screen-starting","#screen-started","#screen-quantity-good","#screen-quantity-defect","#screen-ask-rework","#screen-quantity-rework","#screen-finish-confirm","#screen-finished"]:
  assert x in b,x
def test_only_tutorial_records_selected():
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 b=s[s.index("kioskUser: async page=>"):s.index("calendar: async page=>")]
 # TUT-E06/TUT39-CUT selection now lives in the shared selectTutorialDemoData()
 # helper (called 4x from this block) rather than being inlined here --
 # a DRY refactor, not a removal of the dedicated-fixtures guarantee.
 assert "selectTutorialDemoData(page)" in b
 helper=s[s.index("async function selectTutorialDemoData"):s.index("async function selectTutorialDemoData")+600]
 assert "TUT-E06" in helper and "TUT39-CUT" in helper
def test_visible_labels_vietnamese():
 s=(R/"app/mesflow/web/templates/kiosk.html").read_text()
 assert "Mô phỏng quét QR" in s and "QUÉT CÔNG ĐOẠN" in s
