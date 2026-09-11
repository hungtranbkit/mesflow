#!/usr/bin/env python3
"""Kiểm kê mọi surface dạng list/card/table trong CSS, và chúng đang tự vẽ gì.

Vì sao cần công cụ thay vì đọc mắt: ui.css đã được nén, một dòng chứa hàng chục
rule. Câu hỏi "màn nào đang tự đặt border-radius riêng" không trả lời được bằng
cách nhìn, và mỗi lần trả lời bằng trí nhớ là một lần bỏ sót -- đó chính là lý
do UI lệch nhau sau nhiều đợt audit thủ công.

Chạy: python3 scripts/ui_surface_inventory.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'app' / 'mesflow' / 'web' / 'static' / 'ui.css'

#: Thuộc tính quyết định "trông giống nhau hay không" cho một surface.
VISUAL_PROPS = ('border-radius', 'box-shadow', 'border', 'background', 'padding')

#: Selector nào được coi là surface list/card/table/row. Cố ý rộng: thà liệt kê
#: thừa rồi loại bằng mắt, còn hơn bỏ sót một màn rồi tưởng đã đồng nhất.
SURFACE_HINTS = re.compile(
    r'(card|list|row|table|panel|item|tile|cell|grid|section|box|entry|record)',
    re.IGNORECASE)

COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)


def rules(css: str):
    """(selector, thân rule) cho mọi rule, bỏ qua at-rule lồng nhau ở mức nông."""
    css = COMMENT.sub('', css)
    depth = 0
    buf = []
    selector = []
    for ch in css:
        if ch == '{':
            depth += 1
            if depth == 1:
                selector = ''.join(buf).strip()
                buf = []
                continue
            buf.append(ch)
        elif ch == '}':
            depth -= 1
            if depth == 0:
                yield selector, ''.join(buf)
                buf = []
                continue
            buf.append(ch)
        else:
            buf.append(ch)


def declarations(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for piece in body.split(';'):
        if ':' not in piece:
            continue
        name, _, value = piece.partition(':')
        name = name.strip().lower()
        if name in VISUAL_PROPS:
            out[name] = value.strip()
    return out


def main() -> int:
    css = CSS.read_text(encoding='utf-8')

    surfaces: dict[str, dict[str, str]] = {}
    hardcoded_radius: list[tuple[str, str]] = []
    hardcoded_shadow: list[tuple[str, str]] = []
    bang_important: list[tuple[str, str]] = []
    radius_values: defaultdict[str, int] = defaultdict(int)
    selector_count: defaultdict[str, int] = defaultdict(int)

    for selector, body in rules(css):
        for one in selector.split(','):
            one = one.strip()
            if not one or one.startswith('@') or one.startswith(':root'):
                continue
            selector_count[one] += 1

        decl = declarations(body)
        if not decl:
            continue
        if not SURFACE_HINTS.search(selector):
            continue

        surfaces[selector] = decl

        radius = decl.get('border-radius', '')
        if radius:
            radius_values[radius] += 1
            # 999px / 50% là hình dạng chủ ý (pill, tròn), không phải lệch chuẩn.
            if re.match(r'^[0-9]', radius) and '999' not in radius and '50%' not in radius:
                hardcoded_radius.append((selector, radius))
        shadow = decl.get('box-shadow', '')
        if shadow and 'var(' not in shadow and shadow != 'none':
            hardcoded_shadow.append((selector, shadow))
        for name, value in decl.items():
            if '!important' in value:
                bang_important.append((selector, f'{name}: {value}'))

    duplicates = {sel: n for sel, n in selector_count.items() if n > 1}

    report = {
        'surfaces_total': len(surfaces),
        'hardcoded_radius': sorted(hardcoded_radius),
        'hardcoded_shadow': sorted(hardcoded_shadow),
        'important_on_visual_props': sorted(bang_important),
        'radius_values': dict(sorted(radius_values.items(), key=lambda kv: -kv[1])),
        'duplicate_selectors': dict(sorted(duplicates.items(), key=lambda kv: -kv[1])[:40]),
        'duplicate_selector_total': len(duplicates),
    }

    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"Surface list/card/table có khai báo thị giác : {report['surfaces_total']}")
    print(f"border-radius viết cứng (không token)        : {len(hardcoded_radius)}")
    print(f"box-shadow viết cứng (không token)           : {len(hardcoded_shadow)}")
    print(f"!important trên thuộc tính thị giác          : {len(bang_important)}")
    print(f"Selector bị khai nhiều lần                   : {report['duplicate_selector_total']}")
    print()
    print('Các giá trị border-radius đang dùng:')
    for value, n in report['radius_values'].items():
        flag = '' if 'var(' in value or '999' in value or '50%' in value else '   <-- cứng'
        print(f'  {n:>3}x  {value}{flag}')
    print()
    print('border-radius cứng, theo selector:')
    for selector, value in hardcoded_radius:
        print(f'  {value:<12} {selector[:95]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
