from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_po_modal_uses_available_template_endpoint():
    routes=text('app/mesflow/web/master_data.py')
    js=text('app/mesflow/web/static/app.js')
    assert "@bp.get('/templates/available-for-po')" in routes
    assert 'COUNT(DISTINCT tp.id) AS part_count' in routes
    assert 'COUNT(DISTINCT tpo.id) AS operation_count' in routes
    assert "api('/api/templates/available-for-po')" in js
    assert 'loadAvailablePoTemplates' in js
    assert 'firstReady' in js
    assert 'Part · ${opCount} OP' in js


def test_instantiation_does_not_auto_chain_time_dependencies():
    repo=text('app/mesflow/db/repositories/master_data.py')
    instantiate=repo[repo.index('    def instantiate('):]
    assert 'previous_by_part' not in instantiate
    assert "float(op.get('standard_seconds_per_unit') or 0),None" in instantiate
    assert 'pending_sources' in instantiate
    assert 'input_source_operation_id' in instantiate


def test_demo_seed_only_uses_selected_quantity_links():
    routes=text('app/mesflow/web/master_data.py')
    assert "DEMO_TEMPLATE_SOURCE='DEMO:E10GRE_ROUTER_V2_RELAXED'" in routes
    assert 'DEMO_QUANTITY_LINKS' in routes
    assert "'DEMO-E10-CHI-TIET'" in routes
    assert "'DEMO-E10-LAP-RAP'" in routes
    assert "'DEMO-E10-FULL'" in routes
    assert 'previous_code=None' not in routes[routes.index("@bp.post('/templates/demo/seed')"):]
    assert "source_code=links.get(op_code)" in routes
    assert "version='DEMO-2.0'" in routes
    # 3 + 3 + 5 limited quantity links only.
    block=routes[routes.index('DEMO_QUANTITY_LINKS='):routes.index('DEMO_TEMPLATES=')]
    assert block.count("':'") == 11


def test_demo_seed_updates_old_demo_templates():
    routes=text('app/mesflow/web/master_data.py')
    seed=routes[routes.index("@bp.post('/templates/demo/seed')"):routes.index("@bp.get('/templates/<int:template_id>/tree')")]
    assert "UPDATE templates SET name=%s,product=%s,version='DEMO-2.0'" in seed
    assert "DELETE FROM template_operations WHERE template_id=%s" in seed
    assert "DELETE FROM template_parts WHERE template_id=%s" in seed
    assert 'updated+=1' in seed


def test_release_version_v6588():
    assert tuple(map(int,text('VERSION.txt').strip().split('.'))) >= (65,8,8)
    version=text('VERSION.txt').strip()
    assert f"__version__='{version}'" in text('app/mesflow/__init__.py').replace(' ', '')
    assert f"mesflow-app:{version}" in text('compose.yml')
