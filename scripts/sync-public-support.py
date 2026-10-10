#!/usr/bin/env python3
"""Embed shared FAQ assets so the landing answers even when support is down."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/'services/public-support'
facts=json.loads((SERVICE/'public-facts.json').read_text())
public=[{k:f[k] for k in ('id','label','text','keys','href')} for f in facts]
script=(SERVICE/'assistant.js').read_text().replace('/*PUBLIC_FACTS*/[]',json.dumps(public,ensure_ascii=False))
widget=(SERVICE/'widget.js').read_text()
p=ROOT/'app/mesflow/web/templates/welcome.html';text=p.read_text()
start=text.index('<!-- PUBLIC SUPPORT GENERATED -->');end=text.index('<!-- /PUBLIC SUPPORT GENERATED -->')
updated=text[:start]+'<!-- PUBLIC SUPPORT GENERATED -->\n<script>\n'+script+'\n'+widget+'\n</script>\n'+text[end:]
if '--check' in sys.argv:
 if updated!=text:raise SystemExit('Run scripts/sync-public-support.py')
else:p.write_text(updated)
