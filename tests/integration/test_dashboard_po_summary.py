from mesflow.db.repositories.analytics import DashboardRepository


def _po(rows, po_id):
    return next(row for row in rows if int(row['po_id']) == int(po_id))


def test_po_summary_uses_terminal_operation_without_sequential_double_count(db, seeded_factory):
    g = seeded_factory
    extra_ids, part_ids = [], []
    try:
        with db.cursor() as cur:
            cur.execute("UPDATE operations SET done_qty=100,defect_qty=0,rework_qty=0,sort_order=10 WHERE id=%s", (g['operation_id'],))
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,sort_order,qr,
                predecessor_operation_id,done_qty,defect_qty,rework_qty)
                VALUES(%s,%s,%s,'OP2','IN_PROGRESS',20,%s,%s,80,10,6) RETURNING id""",
                (g['po_id'], g['part_id'], f"TEST-OP2-{g['suffix']}", f"WF|OP|TEST-OP2-{g['suffix']}", g['operation_id']))
            op2 = cur.fetchone()['id']; extra_ids.append(op2)
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,sort_order,qr,
                predecessor_operation_id,done_qty,defect_qty,rework_qty)
                VALUES(%s,%s,%s,'FINAL','IN_PROGRESS',30,%s,%s,70,8,3) RETURNING id""",
                (g['po_id'], g['part_id'], f"TEST-FINAL-{g['suffix']}", f"WF|OP|TEST-FINAL-{g['suffix']}", op2))
            extra_ids.append(cur.fetchone()['id'])

        row = _po(DashboardRepository().po_progress(500), g['po_id'])
        assert (row['good_quantity'], row['defect_quantity'], row['repairable_quantity']) == (70, 8, 3)
        assert (row['scrap_quantity'], row['remaining_quantity']) == (5, 30)
        assert float(row['progress_percent']) == 70.0
        assert row['good_quantity'] != 250

        with db.cursor() as cur:
            cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Second Part') RETURNING id",
                        (g['po_id'], f"TEST-PART2-{g['suffix']}"))
            part2 = cur.fetchone()['id']; part_ids.append(part2)
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,sort_order,qr,
                done_qty,defect_qty,rework_qty) VALUES(%s,%s,%s,'PART2 FINAL','IN_PROGRESS',10,%s,50,10,10) RETURNING id""",
                (g['po_id'], part2, f"TEST-P2-FINAL-{g['suffix']}", f"WF|OP|TEST-P2-FINAL-{g['suffix']}"))
            extra_ids.append(cur.fetchone()['id'])
        row = _po(DashboardRepository().po_progress(500), g['po_id'])
        assert (row['good_quantity'], row['defect_quantity'], row['repairable_quantity']) == (60, 18, 13)
        assert row['scrap_quantity'] == 5
        assert float(row['progress_percent']) == 60.0
    finally:
        with db.cursor() as cur:
            if extra_ids: cur.execute('DELETE FROM operations WHERE id=ANY(%s)', (extra_ids,))
            if part_ids: cur.execute('DELETE FROM parts WHERE id=ANY(%s)', (part_ids,))


def test_po_scrap_variants_and_large_quantities(db, seeded_factory):
    g = seeded_factory
    for defect, repairable, expected_scrap in ((0, 0, 0), (10, 0, 10), (10, 10, 0), (10, 4, 6)):
        with db.cursor() as cur:
            cur.execute('UPDATE operations SET done_qty=999999,defect_qty=%s,rework_qty=%s WHERE id=%s',
                        (defect, repairable, g['operation_id']))
        row = _po(DashboardRepository().po_progress(500), g['po_id'])
        assert (row['defect_quantity'], row['repairable_quantity'], row['scrap_quantity']) == (defect, repairable, expected_scrap)
        assert float(row['progress_percent']) == 100.0
