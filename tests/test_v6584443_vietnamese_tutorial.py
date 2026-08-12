from pathlib import Path
R=Path(__file__).resolve().parents[1]
def test_version(): assert (R/"VERSION.txt").read_text().strip()=="65.8.44.43"
def test_exception_voice():
 s=(R/"tutorial/narration/06_session_exceptions.txt").read_text()
 for x in ["OPEN_TOO_LONG","ZERO_QTY_LONG","MISSING_STATION","OVERLAP","INVALID_TIME","IN_PROGRESS","RESOLVED"]: assert x not in s
 assert "Phiên làm việc bất thường" in s and "đang xử lý" in s
def test_core_english_removed_from_voice():
 s="\n".join(p.read_text() for p in (R/"tutorial/narration").glob("*.txt"))
 for x in ["Dashboard","Production Order","Template","Material Flow","Operation","Session","Kiosk","workflow","heartbeat","trace ID"]: assert x not in s, x
def test_glossary(): assert "Session → Phiên làm việc" in (R/"tutorial/VIETNAMESE_GLOSSARY.md").read_text()
