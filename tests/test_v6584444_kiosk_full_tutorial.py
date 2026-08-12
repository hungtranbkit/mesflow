from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E="65.8.44.44"
def test_version():
 assert (R/"VERSION.txt").read_text().strip()==E
 assert E in (R/"app/mesflow/__init__.py").read_text()
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
 assert "TUT-E06" in b and "TUT39-CUT" in b
def test_visible_labels_vietnamese():
 s=(R/"app/mesflow/web/templates/kiosk.html").read_text()
 assert "Mô phỏng quét QR" in s and "QUÉT CÔNG ĐOẠN" in s
