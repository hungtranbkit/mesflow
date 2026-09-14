"""Archive of the Excel workbooks Templates were imported from.

Why this exists: `templates.source_workbook` only ever held the uploaded
file's NAME, overwritten on every re-import. When TPL-6126 turned out to
contain ten duplicate Operation codes (2026-09-09) there was no way to open
the sheet that produced it, nor to tell which upload was responsible. A
failed import left no trace at all.

Every import ATTEMPT is recorded here, including failures -- a workbook that
was rejected is precisely the one someone needs to look at. The bytes are
stored once per distinct file (content-addressed by sha256) on the same
uploads volume the Part drawings already use; the row keeps the pointer, who
did it, and what came out.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from mesflow.db.connection import fetch_all, fetch_one, transaction

# Sibling of /data/uploads/template-parts (see web/master_data.py), so both
# kinds of uploaded file live under the one volume that is already backed up.
STORAGE_ROOT = Path('/data/uploads/template-imports')

OUTCOME_CREATED = 'CREATED'
OUTCOME_REPLACED = 'REPLACED'
OUTCOME_FAILED = 'FAILED'


def _safe_name(filename: str) -> str:
    """Keep something human-readable, drop anything path-like."""
    stem = Path(str(filename or 'workbook.xlsx')).name
    cleaned = ''.join(ch if (ch.isalnum() or ch in '-_. ') else '_' for ch in stem).strip()
    return (cleaned or 'workbook.xlsx')[:120]


class TemplateImportRepository:
    def record(self, *, data: bytes, filename: str, outcome: str,
               template_id=None, template_code: str = '', error_message: str = '',
               part_count: int = 0, operation_count: int = 0,
               duplicate_operation_codes: str = '',
               actor_user_id=None, actor_username: str = ''):
        """Store the workbook (once per distinct content) and log the attempt.

        Called for successes and failures alike, and deliberately outside the
        import's own transaction: a rejected workbook is rolled back as far as
        the Template is concerned, but the evidence of the attempt must
        survive that rollback.
        """
        digest = hashlib.sha256(data).hexdigest()
        with transaction() as conn:
            blob = conn.execute('SELECT id,storage_path FROM template_import_blobs WHERE sha256=%s',
                                (digest,)).fetchone()
            if blob:
                blob_id = blob['id']
                stored = Path(blob['storage_path'])
            else:
                stamp = datetime.now(timezone.utc)
                folder = STORAGE_ROOT / f'{stamp:%Y}' / f'{stamp:%m}'
                stored = folder / f'{digest[:16]}-{_safe_name(filename)}'
                blob_id = conn.execute(
                    'INSERT INTO template_import_blobs(sha256,byte_size,storage_path) VALUES(%s,%s,%s) RETURNING id',
                    (digest, len(data), str(stored))).fetchone()['id']
            # Written after the row is reserved but inside the transaction, so
            # a failed write rolls the pointer back rather than leaving a row
            # that promises a file which is not there.
            if not stored.exists():
                stored.parent.mkdir(parents=True, exist_ok=True)
                stored.write_bytes(data)
            event = conn.execute("""INSERT INTO template_import_events(
                    blob_id,template_id,template_code,original_filename,outcome,error_message,
                    part_count,operation_count,duplicate_operation_codes,actor_user_id,actor_username)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,created_at""",
                (blob_id, template_id, str(template_code or ''), str(filename or ''), outcome,
                 str(error_message or '')[:2000], int(part_count or 0), int(operation_count or 0),
                 str(duplicate_operation_codes or ''), actor_user_id, str(actor_username or ''))).fetchone()
        return {'import_id': event['id'], 'sha256': digest, 'stored_path': str(stored)}

    def list(self, *, template_id=None, template_code: str = '', limit: int = 200):
        conditions, params = [], []
        if template_id:
            # Match by id OR by code: a failed import has no template_id, and a
            # template that was deleted and re-imported keeps its history under
            # the same code.
            row = fetch_one('SELECT code FROM templates WHERE id=%s', (int(template_id),))
            if row and row.get('code'):
                conditions.append('(e.template_id=%s OR upper(e.template_code)=upper(%s))')
                params += [int(template_id), row['code']]
            else:
                conditions.append('e.template_id=%s')
                params.append(int(template_id))
        if template_code:
            conditions.append('upper(e.template_code)=upper(%s)')
            params.append(str(template_code))
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params.append(min(max(int(limit), 1), 1000))
        return fetch_all(f"""SELECT e.id,e.template_id,e.template_code,e.original_filename,e.outcome,
                e.error_message,e.part_count,e.operation_count,e.duplicate_operation_codes,
                e.actor_username,e.created_at,b.sha256,b.byte_size
            FROM template_import_events e JOIN template_import_blobs b ON b.id=e.blob_id
            {where} ORDER BY e.created_at DESC,e.id DESC LIMIT %s""", tuple(params))

    def file_for(self, import_id: int):
        row = fetch_one("""SELECT e.original_filename,b.storage_path,b.byte_size
            FROM template_import_events e JOIN template_import_blobs b ON b.id=e.blob_id
            WHERE e.id=%s""", (int(import_id),))
        return row

    def source_workbook_for(self, template_id: int):
        """The workbook THIS Template was built from -- by link, never by name.

        Matching on `original_filename` would be a coin toss: on the live TEST
        box seven distinct blobs share the name 'Lộ trình sản xuất NEWARK ARM
        CHAIR .xlsx', differing by a few hundred bytes each. Opening the wrong
        one backfills row numbers that point at the wrong rows -- worse than
        showing nothing, because it looks right.

        Two sources of truth, in order:

        1. `template_source_workbooks` (0052) -- the link written INSIDE the
           import's own transaction, so it can only exist for a Template that
           exists. Newest wins: a re-import links the newer file.
        2. `template_import_events` (0046) -- the fallback for Templates
           imported before 0052 existed. Only CREATED/REPLACED: a FAILED
           attempt wrote no Operation, so its rows cannot be the ones on
           screen. Still keyed on `template_id`, never on the filename.

        Returns None when nothing links, so the caller can say WHY rather than
        guess. The row carries `link_source` for exactly that reason.
        """
        row = fetch_one("""SELECT b.id blob_id,b.sha256,b.byte_size,b.storage_path,
                w.original_filename,w.linked_at AS at,'template_source_workbooks' AS link_source
            FROM template_source_workbooks w JOIN template_import_blobs b ON b.id=w.blob_id
            WHERE w.template_id=%s ORDER BY w.linked_at DESC,w.id DESC LIMIT 1""",
            (int(template_id),))
        if row:
            return row
        return fetch_one("""SELECT b.id blob_id,b.sha256,b.byte_size,b.storage_path,
                e.original_filename,e.created_at AS at,'template_import_events' AS link_source
            FROM template_import_events e JOIN template_import_blobs b ON b.id=e.blob_id
            WHERE e.template_id=%s AND e.outcome IN (%s,%s)
            ORDER BY e.created_at DESC,e.id DESC LIMIT 1""",
            (int(template_id), OUTCOME_CREATED, OUTCOME_REPLACED))
