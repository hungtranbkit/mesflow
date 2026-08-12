from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')


def test_visible_add_part_action_exists():
    assert '+ Thêm Part' in JS
    assert 'tplAddPart' in JS
    assert 'ps.push' in JS
    assert 'applyOldParts' in JS


def test_part_is_saved_to_template_tree_api():
    assert "api(`/api/templates/${id}/tree`,{method:'PUT'" in JS
    assert 'treePayload' in JS
    assert 'part_key' in JS
