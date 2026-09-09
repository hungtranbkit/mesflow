"""No database error text ever reaches the screen.

Reported on TEST 2026-09-09: creating a PO from a Template popped
`duplicate key value violates unique constraint "operations_code_key"
DETAIL: Key (code)=(6126-KM-3172005-08-OP02) already exists.` at the user.
That text is written for whoever wrote the schema; it says nothing about what
to do next and leaks table/constraint names to the shop floor.
"""
import psycopg
import pytest

from mesflow.web.errors import _database_message


@pytest.mark.parametrize('cls_name', ['UniqueViolation', 'ForeignKeyViolation',
                                      'NotNullViolation', 'CheckViolation'])
def test_every_constraint_class_gets_a_vietnamese_sentence(cls_name):
    message = _database_message(getattr(psycopg.errors, cls_name)('raw postgres text'))
    assert message
    # Vietnamese, actionable, and none of the driver's own words.
    lowered = message.lower()
    for leak in ('duplicate key', 'unique constraint', 'violates', 'detail:',
                 'psycopg', 'sqlstate', 'null value', 'foreign key'):
        assert leak not in lowered, f'{cls_name} leaked driver text: {message}'
    assert any(word in lowered for word in ('thử lại', 'kiểm tra', 'không thực hiện được'))


def test_known_constraints_name_the_thing_the_user_recognises():
    from mesflow.web.errors import _CONSTRAINT_MESSAGES
    assert 'operations_code_key' in _CONSTRAINT_MESSAGES
    for constraint, message in _CONSTRAINT_MESSAGES.items():
        assert constraint not in message, f'{constraint}: constraint name leaked into the message'
        assert message.strip().endswith('.')


def test_generic_fallback_is_not_english_boilerplate():
    message = _database_message(psycopg.errors.IntegrityError('raw'))
    assert 'raw' not in message
    assert 'ràng buộc' in message.lower()
