from mesflow.db.repositories.master_data import (
    TemplateValidationError,
    _normalize_part_code,
    _validate_template_part_codes,
)


def test_normalize_part_code_trim_and_upper():
    assert _normalize_part_code(' part-001 ') == 'PART-001'


def test_unique_part_codes_are_valid():
    assert _validate_template_part_codes([{'code':'PART-001'},{'code':'PART-002'}]) == ['PART-001','PART-002']


def test_duplicate_part_codes_are_rejected_case_insensitive():
    try:
        _validate_template_part_codes([{'code':'PART-001'},{'code':'part-001'}],template={'id':41,'code':'TPL'})
        assert False, 'expected validation error'
    except TemplateValidationError as exc:
        assert exc.code == 'DUPLICATE_PART_CODE_IN_TEMPLATE'
        assert exc.details['duplicate_codes'] == ['PART-001']
        assert exc.details['template_id'] == 41


def test_duplicate_part_codes_are_rejected_after_trim():
    try:
        _validate_template_part_codes([{'code':'PART-001'},{'code':' PART-001 '}])
        assert False, 'expected validation error'
    except TemplateValidationError as exc:
        assert exc.details['duplicate_codes'] == ['PART-001']


def test_empty_part_code_is_rejected():
    for value in (None,'','   '):
        try:
            _validate_template_part_codes([{'code':value}])
            assert False, 'expected validation error'
        except TemplateValidationError as exc:
            assert exc.code == 'EMPTY_PART_CODE'
