from pathlib import Path

import pytest


STATIC_HINTS=('read_text(','.read_text()',"open('",'open("')
BEHAVIOR_FILES={
    'test_production_state_integrity.py',
    'test_production_consistency_p1.py',
    'test_scheduling_time_p2.py',
    'test_session_overlap_and_exceptions.py',
    'test_session_exception_workflow.py',
    'test_shift_dashboard.py',
    'test_super_admin_system_console.py',
}


def pytest_collection_modifyitems(items):
    """Keep CI groups explicit without forcing every historical file rewrite at once."""
    for item in items:
        path=Path(str(item.path))
        if 'integration' in path.parts:
            item.add_marker(pytest.mark.integration)
            if path.name in BEHAVIOR_FILES:item.add_marker(pytest.mark.behavior)
            continue
        try:source=path.read_text(encoding='utf-8')
        except OSError:source=''
        item.add_marker(pytest.mark.static if any(hint in source for hint in STATIC_HINTS) else pytest.mark.unit)
