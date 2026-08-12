from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
REPO=(ROOT/'app/mesflow/db/repositories/master_data.py').read_text(encoding='utf-8')


def test_template_crud_ui_present():
    for text in ('+ Template mới','newTemplateOld','saveTemplateOld','cloneTemplateOld','tplDelete'):
        assert text in JS


def test_template_tree_ui_supports_part_operation_equipment_crud():
    for text in ('tplAddPart','data-add-op','data-remove-part','data-remove-op','equipment_code'):
        assert text in JS
    assert "api('/api/equipment?limit=1000')" in JS


def test_template_instantiate_uses_full_modal():
    for text in ('showInstantiateTemplateModal','planned_quantity','sales_order_id','due_date','priority','notes'):
        assert text in JS


def test_template_repository_validates_payload():
    for text in ('template code required','duplicate part code','operation references invalid part','duplicate template equipment'):
        assert text in REPO
