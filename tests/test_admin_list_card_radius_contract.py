"""ADMIN / MASTER DATA list+card surfaces share one rounding scale.

WHAT THIS LOCKS DOWN, and why it is written the way it is.

The rounding of a card is NOT decided by each component's own rule. One
suffix-scanning rule in ui.css owns it:

    .admin-body :where(.card,[class$="-card"],...):where(:not(.part-block)){
        border-radius:var(--radius-card)!important; ... }

That rule exists precisely because hand-maintained per-component lists drift
("mỗi màn một radius/shadow"). So asserting a literal radius on each component
would be testing the wrong layer -- a component can declare anything and still
render 7px. What this file asserts instead:

  1. the token scale is declared once in :root,
  2. the suffix rule that enforces card shape still exists and still points at
     the token,
  3. containers that are NOT covered by that rule (the shared Part/Operation
     primitive) use a container token, never a control token,
  4. the design contract is written down.

Runtime proof that the rendered pixels agree lives in
tests/e2e/admin-list-card-consistency.spec.js, which measures computed style.

NEGATIVE PROOF: put `--radius-control` back on `.op-list` and
`test_op_list_container_uses_a_container_radius` fails. Drop the suffix rule
and `test_card_shape_is_owned_by_one_rule` fails.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / 'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')

#: Canonical surface steps (see tests/test_ui_surface_radius_is_canonical.py).
#: --radius-card/panel/row are LEGACY names, kept only for small elements
#: (sidebar icons, gantt bars, badges) and explicitly not for a content surface.
CONTAINER_RADII = ('var(--radius-surface)', 'var(--radius-surface-row)')


def _block(selector: str) -> str:
    """The declaration body of the rule whose selector *is* this selector."""
    for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS):
        s = sel.strip().replace('\n', ' ')
        if s.startswith('@'):
            continue
        if selector in [p.strip() for p in s.split(',')] or s.endswith(selector):
            if 'border-radius' in body:
                return body
    return ''


def test_root_declares_the_radius_scale_once():
    for token in ('--radius-surface', '--radius-surface-row', '--radius-control'):
        assert f'{token}:' in CSS, f'{token} missing from :root'


def test_card_shape_is_owned_by_one_rule():
    """The suffix-scanning rule is the single source of card shape."""
    m = re.search(r'\.admin-body :where\(\.card,\[class\$="-card"\][^{]*\{([^}]*)\}', CSS)
    assert m, 'the [class$="-card"] rule that owns card shape is gone'
    body = m.group(1)
    assert 'border-radius:var(--radius-surface)!important' in body, body
    # .part-block defines its own shape and must stay excluded, or the Part
    # block at PO detail and at Template editor drift apart again.
    assert ':not(.part-block)' in CSS


def test_op_list_container_uses_a_container_radius():
    """Shared Part/Operation primitive: tier-2 list is a container, not a control.

    Measured live on PO detail when this was first found: .part-block 7px,
    .op-list-head 7px, .op-list 5px -- the header's corners were rounder than
    the box clipping them. The integration lane has since pinned .op-list at
    --radius-surface-row, which is the same conclusion in the canonical
    vocabulary; this keeps it from drifting back to a control-sized step.
    """
    body = _block('.op-list')
    assert body, '.op-list declares no border-radius'
    m = re.search(r'border-radius\s*:\s*([^;]+)', body)
    value = m.group(1).strip()
    assert value in CONTAINER_RADII, (
        f'.op-list is a list container inside .part-block; it must not use a '
        f'control-sized radius. Got: {value}'
    )
    assert 'var(--radius-control)' not in value


def test_po_operation_header_matches_the_list_it_heads():
    """.po-op-header is the first child of .op-list and is clipped by it.

    It must take the same step as its container rather than a hardcoded 6px or
    a legacy token -- otherwise the header's corners and the box cutting them
    disagree again.
    """
    header = _block('.po-op-header')
    assert header
    assert 'var(--radius-surface-row)' in header, header
    assert '6px 6px 0 0' not in header
    assert 'var(--radius-card)' not in header, 'legacy token on a content surface'
    op_list = _block('.op-list')
    assert 'var(--radius-surface-row)' in op_list, op_list


def test_design_contract_is_recorded():
    # Dockerfile.test does not copy DESIGN.md into the test image (it copies
    # app/, tests/, scripts/ and a named list of files). Caught by running the
    # canonical docker gate: this test passed on a host checkout and failed in
    # the image. Same convention as test_artifact_metadata_contract.py for
    # PROJECT.yaml -- skip where the file cannot exist, rather than pretend.
    design_md = ROOT / 'DESIGN.md'
    if not design_md.is_file():
        pytest.skip('DESIGN.md not present in this test image -- run from a real checkout')
    design = design_md.read_text(encoding='utf-8')
    assert 'List/card nhất quán' in design
    assert 'test_admin_list_card_radius_contract.py' in design
    # the stale second radius scale must not come back
    assert 'Control radius 4px; panel 6px; overlay 8px' not in design
