from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/"app/mesflow/web/static/app.js").read_text()
CSS=(ROOT/"app/mesflow/web/static/ui.css").read_text()
def test_setup_is_nested_by_parent():
 assert "function poOperationDisplayRows(ops)" in JS
 assert "Number(o.parent_operation_id||0)" in JS
 assert "byParent.get(Number(o.id))" in JS
 assert "ops.map((o,i)=>poOperationRow(o,i)).join('')" not in JS
def test_setup_child_visual_contract():
 assert "is-setup is-linked-setup" in JS
 assert "Setup đi kèm" in JS and "op-setup-parent" in JS
 assert 'content:"└─"' in CSS
def test_orphan_setup_is_visible_as_config_problem():
 assert "Setup chưa gắn Operation" in JS
 assert "Cần kiểm tra cấu hình liên kết" in JS
 assert "is-orphan-setup" in JS
def test_toggle_copy_describes_relationship():
 assert "Hiện Setup / sửa hàng đi kèm Operation" in JS
