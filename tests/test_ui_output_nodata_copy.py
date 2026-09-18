from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_unrecorded_output_uses_single_natural_phrase_without_touching_zero_rule():
    core = (ROOT / "app/mesflow/web/static/core/ui.js").read_text()
    assert "const text='Chưa ghi nhận sản lượng'" in core
    assert "const text=`Đạt ${QTY_UNKNOWN} · NG ${QTY_UNKNOWN}`" not in core
    assert "Đạt 0 · NG 0" in (ROOT / "tests/e2e/qty-recorded-vs-zero.spec.js").read_text()
