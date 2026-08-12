from pathlib import Path


def test_running_card_declared_before_use():
    text = Path("app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    declaration = "const runningCard=x=>"
    usage = ".map(runningCard)"
    assert declaration in text
    assert usage in text
    assert text.index(declaration) < text.index(usage)
