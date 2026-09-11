"""The kiosk's per-code help must be able to reach the screen.

ERROR_HELP in kiosk.js is a curated, worker-facing next step for each
error_code. It was dead code for every API error: workerError() branched only
on the HTTP status, and api() assigned error.action from whatever it returned,
so the code-keyed table was never consulted. An ambiguous employee badge and an
ambiguous Operation label both rendered the generic 409 line.

NEGATIVE PROOF: delete the `ERROR_HELP[code]` lookup from workerError() and
test_worker_error_prefers_the_error_code fails; the behavioural half is
tests/e2e/kiosk-web-error-guidance.spec.js.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
PY_SRC = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')


def test_worker_error_prefers_the_error_code():
    body = re.search(r'function workerError\(data,status\)\s*\{(.*?)\n  \}', JS, re.S)
    assert body, 'workerError() not found'
    src = body.group(1)
    assert 'ERROR_HELP[code]' in src, (
        'workerError() must consult ERROR_HELP by error_code, otherwise the '
        'whole table is unreachable and every API error falls back to an '
        'HTTP-status guess'
    )
    # The auth branch has to stay ahead of it.
    assert src.index('status===401||status===403') < src.index('ERROR_HELP[code]')


def test_every_code_the_backend_emits_has_worker_help():
    """A code with no entry silently drops back to the status guess."""
    emitted = set(re.findall(r"error_code='([A-Z]{3}-\d{3})'", PY_SRC))
    helped = set(re.findall(r"'([A-Z]{3}-\d{3})':", JS))
    missing = sorted(emitted - helped)
    assert not missing, f'kiosk.py emits these codes with no ERROR_HELP entry: {missing}'


def test_ambiguity_is_refused_not_guessed():
    """Operation identity: code is display-only and may repeat across Parts."""
    assert 'AmbiguousOperationQR' in PY_SRC and 'AmbiguousEmployeeQR' in PY_SRC
    assert "error_code='OP-002'" in PY_SRC
    assert "error_code='EMP-002'" in PY_SRC
    # resolve_* is the shared resolver; no LIMIT 1 guessing may come back.
    assert 'resolve_operation_id' in PY_SRC and 'resolve_employee_id' in PY_SRC


def _code_only(source: str) -> str:
    """Drop whole-line `#` comments.

    kiosk.py's own comment deliberately NAMES the removed SETUP_REQUIRED /
    OP-010 error to record that production is no longer gated on setup state;
    only executable code may be searched for it.
    """
    return '\n'.join(l for l in source.splitlines() if not l.lstrip().startswith('#'))


def test_setup_does_not_block_production_at_the_kiosk():
    """SETUP is an independent Operation, never a prerequisite gate."""
    code = _code_only(PY_SRC)
    assert 'SETUP_REQUIRED' not in code
    assert 'OP-010' not in code
