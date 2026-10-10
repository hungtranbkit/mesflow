"""Bounded subprocess renderer: accepts already-authorized snapshot JSON only."""
import html
import json
import sys


def render(record):
    from weasyprint import HTML
    def deny_url(*_args, **_kwargs):
        raise ValueError('External resources disabled')
    esc = lambda value: html.escape(str(value if value is not None else ''))
    headings = ''.join('<th>' + esc(key) + '</th>' for key in record['columns'])
    rows = ''.join('<tr>' + ''.join('<td>' + esc(row.get(key)) + '</td>' for key in record['columns']) + '</tr>' for row in record['rows'])
    document = '''<!doctype html><meta charset="utf-8"><style>
    @page {size:A4 landscape; margin:12mm; @bottom-right {content:counter(page)}}
    body {font-family:"DejaVu Sans",sans-serif;font-size:8pt} table {width:100%;border-collapse:collapse;table-layout:fixed}
    td,th {border:1px solid #999;padding:4px;overflow-wrap:anywhere} thead {display:table-header-group}
    tr {break-inside:avoid} pre {white-space:pre-wrap;overflow-wrap:anywhere}
    </style>'''
    document += '<h1>' + ('DEMO — DỮ LIỆU MẪU' if record['mode'] == 'demo' else 'BÁO CÁO MES') + '</h1>'
    document += '<pre>' + esc(json.dumps({'filters': record['intent'], 'generated_at': record['generated_at'],
                                        'snapshot': record.get('snapshot'), 'sources': record['sources']}, ensure_ascii=False)) + '</pre>'
    document += '<table><thead><tr>' + headings + '</tr></thead><tbody>' + rows + '</tbody></table>'
    document += '<p>' + esc('\n'.join(record['notes'])) + '</p>'
    return HTML(string=document, url_fetcher=deny_url).write_pdf()


if __name__ == '__main__':
    raw = sys.stdin.buffer.read(1_000_001)
    if len(raw) > 1_000_000: raise ValueError('input bound')
    record = json.loads(raw)
    if len(record['rows']) > 200: raise ValueError('row bound')
    sys.stdout.buffer.write(render(record))
