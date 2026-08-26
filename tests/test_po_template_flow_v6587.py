from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_schema_links_po_to_template():
    migration=text('app/migrations/versions/0015_po_template_source.py')
    assert "revision='0015'" in migration
    assert "down_revision='0014'" in migration
    assert "source_template_id" in migration
    assert "source_template_code" in migration
    assert "source_template_version" in migration
    assert "ondelete='SET NULL'" in migration


def test_po_create_is_template_driven():
    repo=text('app/mesflow/db/repositories/master_data.py')
    routes=text('app/mesflow/web/master_data.py')
    assert 'Production Order phải được tạo từ Template' in repo
    assert "if resource=='production-orders'" in routes
    assert "TemplateTreeRepository().instantiate" in routes
    assert "source_template_id,source_template_code,source_template_version" in repo
    assert "Template chưa có Operation" in repo
    assert "operations_created" in repo


def test_po_ui_requires_template_and_op_preview():
    js=text('app/mesflow/web/static/app.js')
    assert '+ Tạo PO từ Template' in js
    assert 'Tạo Production Order từ Template' in js
    assert 'name="template_id"' in js
    assert '/tree`)' in js
    assert 'Tạo PO và sao chép OP' in js
    assert 'source_template_code' in js
    assert 'await openProductionOrder(Number(result.production_order_id))' in js


def test_excel_import_does_not_create_empty_po():
    source=text('app/mesflow/web/excel_io.py')
    assert 'Hãy tạo PO từ Template trước khi import Operation' in source
    assert "VALUES(%s,%s,%s,'PLANNED','NORMAL','Tạo từ Excel')" not in source


def test_release_version():
    version=text('VERSION.txt').strip()
    assert tuple(map(int,version.split('.'))) >= (65,8,33)
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==version
    assert f"mesflow-app:{version}" in text('compose.yml')
