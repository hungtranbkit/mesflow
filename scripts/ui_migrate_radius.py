#!/usr/bin/env python3
"""Hội tụ border-radius của các surface về thang canonical.

Hai loại thay đổi, cố ý tách bạch:

  XOÁ   -- khai báo đã CHẾT: selector nằm trong tầm rule quét
           `.admin-body :where(.card,[class$="-card"],...)` vốn đặt
           `border-radius ... !important`, nên giá trị viết tại chỗ không bao
           giờ có hiệu lực. Giữ chúng lại chỉ làm người đọc tin nhầm rằng màn
           đó đang bo 14px trong khi thực tế ra 7px -- đúng cái vòng lặp khiến
           mỗi lần "sửa một màn" lại không ăn.

  ĐỔI   -- khai báo còn SỐNG nhưng viết số cứng: đổi sang token theo bậc.

Chạy: python3 scripts/ui_migrate_radius.py [--check]
`--check` chỉ báo cáo, không ghi -- dùng cho test.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'app' / 'mesflow' / 'web' / 'static' / 'ui.css'

#: Selector có khai báo radius đã bị rule quét ghi đè -> xoá khai báo.
DEAD = [
    '.card,.panel',
    '.template-old-list-panel',
    '.template-old-card',
    '.flow-card',
    '.kiosk-card',
    '.recent-op-card',
    '.shift-config-card',
    '.qr-catalog-card',
    '.pc-po-card',
    '.ec-card',
    '.mf-relation-card',
    '.tutorial-card',
    '.tutorial-player-card',
    '.ba-card',
]

#: Selector còn sống, viết số cứng -> token theo bậc.
RETARGET = {
    # khối nội dung ngoài cùng
    '.builder-section': 'var(--radius-surface)',
    '.kiosk-panel': 'var(--radius-surface)',
    # khối lồng bên trong một surface
    '.overview-item': 'var(--radius-surface-row)',
    '.pc-op-row': 'var(--radius-surface-row)',
    '.qr-preview-box': 'var(--radius-surface-row)',
    # điều khiển
    '.login-card input,.modal input,.modal select,.modal textarea': 'var(--radius-control)',
    '.login-card button,.primary': 'var(--radius-control)',
    '.template-flow-row select': 'var(--radius-control)',
    ('.session-manage-filter select,.session-manage-filter input,.session-edit-grid select,'
     '.session-edit-grid input,.session-edit-grid textarea'): 'var(--radius-control)',
}

RULE = re.compile(r'([^{}]+)\{([^{}]*)\}')
RADIUS = re.compile(r'border-radius:\s*[^;}]+;?')


def migrate(css: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    def handle(match: re.Match[str]) -> str:
        selector, body = match.group(1), match.group(2)
        key = selector.strip()
        if 'border-radius' not in body:
            return match.group(0)
        if key in DEAD:
            new_body = RADIUS.sub('', body, count=1).replace(';;', ';')
            if new_body != body:
                changes.append(f'XOÁ (đã chết)  {key}')
                return f'{selector}{{{new_body}}}'
        if key in RETARGET:
            token = RETARGET[key]
            new_body = RADIUS.sub(f'border-radius:{token};', body, count=1)
            if new_body != body:
                changes.append(f'ĐỔI -> {token:<28} {key[:60]}')
                return f'{selector}{{{new_body}}}'
        return match.group(0)

    return RULE.sub(handle, css), changes


def main() -> int:
    css = CSS.read_text(encoding='utf-8')
    migrated, changes = migrate(css)
    for line in changes:
        print(' ', line)
    print(f'\nTổng thay đổi: {len(changes)}')
    if '--check' not in sys.argv:
        CSS.write_text(migrated, encoding='utf-8')
        print('Đã ghi ui.css')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
