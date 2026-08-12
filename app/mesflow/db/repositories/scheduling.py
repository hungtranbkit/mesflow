from __future__ import annotations
from datetime import date,datetime,time,timedelta
from mesflow.core.time_policy import coerce_utc,utc_now

RUNNABLE_STATUSES={'DRAFT','PLANNED','RELEASED','READY','IN_PROGRESS'}
RUNNABLE_PO_STATUSES={'RELEASED','IN_PROGRESS','ACTIVE'}
TERMINAL_STATUSES={'COMPLETED','CANCELLED'}

def as_utc(value):
    if value is None:return None
    if isinstance(value,(date,datetime)):return coerce_utc(value,date_time=time(23,59,59))
    return None

def get_available_input(row:dict,predecessor:dict|None=None)->dict:
    plan=max(int(row.get('planned_quantity') or 0),0);good=max(int(row.get('done_qty') or 0),0);defect=max(int(row.get('defect_qty') or 0),0)
    reported=good+defect
    if row.get('input_flow_enabled') and row.get('input_source_operation_id'):
        return {'available_input_qty':max(int(row.get('input_available_qty') or 0),0),'wip_source':'PRODUCTION_LEDGER'}
    elif predecessor:
        supplied=max(int(predecessor.get('done_qty') or 0),0);wip=max(supplied-reported,0);source='PREDECESSOR'
    else:
        wip=max(plan-reported,0);source='PLANNED_QUANTITY_FALLBACK'
    return {'available_input_qty':wip,'wip_source':source}

def operation_wip(row:dict,predecessor:dict|None=None)->dict:
    status=str(row.get('operation_status') or row.get('status') or '').upper();po_status=str(row.get('po_status') or '').upper()
    available=get_available_input(row,predecessor);wip=available['available_input_qty'];source=available['wip_source']
    if po_status not in RUNNABLE_PO_STATUSES and not predecessor and source=='PLANNED_QUANTITY_FALLBACK':wip=0
    dependency_ready=not predecessor or wip>0 or str(predecessor.get('operation_status') or predecessor.get('status') or '').upper()=='COMPLETED'
    status_ready=status in RUNNABLE_STATUSES and status not in TERMINAL_STATUSES
    actionable=bool(status_ready and po_status in RUNNABLE_PO_STATUSES and dependency_ready and wip>0)
    reason='READY' if actionable else ('TERMINAL' if status in TERMINAL_STATUSES else 'PO_NOT_RELEASED' if po_status not in RUNNABLE_PO_STATUSES else 'DEPENDENCY_NOT_READY' if not dependency_ready else 'NO_WIP')
    return {'wip_qty':wip,'wip_source':source,'dependency_ready':dependency_ready,'status_ready':status_ready,'actionable':actionable,'readiness_reason':reason}

def priority_for_operation(row:dict,predecessor:dict|None=None,now:datetime|None=None)->dict:
    now=as_utc(now) or utc_now();readiness=operation_wip(row,predecessor)
    start=as_utc(row.get('planned_start_at') or row.get('calculated_start_at'));end=as_utc(row.get('planned_end_at') or row.get('calculated_end_at'))
    plan=max(int(row.get('planned_quantity') or 0),0);good=max(int(row.get('done_qty') or 0),0);remaining=max(plan-good,0);cycle=max(float(row.get('standard_seconds_per_unit') or 0),0.0);workload=remaining*cycle
    score=0.0;reasons=[];lateness_seconds=0.0
    if end and now>end:
        lateness_seconds=(now-end).total_seconds();score+=min(55.0,20.0+lateness_seconds/3600*2);reasons.append(f'OP trễ {lateness_seconds/3600:.1f} giờ')
    elif start and now<start:
        hours=(start-now).total_seconds()/3600;score+=max(0.0,8.0-hours/3);reasons.append(f'Chưa tới lịch, còn {hours:.1f} giờ')
    elif start and end and end>start:
        elapsed=min(max((now-start).total_seconds()/(end-start).total_seconds(),0),1);score+=12+18*elapsed;reasons.append('Đang trong cửa sổ kế hoạch')
    elif end:
        hours=max((end-now).total_seconds()/3600,0);score+=max(0,18-hours/6);reasons.append('Fallback theo thời điểm kết thúc OP')
    else:
        score+=5;reasons.append('Fallback theo routing/order')
    if end and workload>0:
        available=max((end-now).total_seconds(),1);pressure=workload/available;score+=min(25,pressure*18);reasons.append(f'Còn {remaining} SP / {workload/3600:.1f} giờ tải')
    if readiness['wip_qty']>0:score+=min(15,5+readiness['wip_qty']/max(plan,1)*10)
    planning=max(round(score,1),0);dispatch=planning if readiness['actionable'] else 0.0
    if not readiness['actionable']:reasons.append('Không actionable: '+readiness['readiness_reason'])
    return {**readiness,'planning_priority_score':planning,'dispatch_priority_score':round(dispatch,1),'priority_score':round(dispatch,1),
      'schedule_lateness_seconds':int(lateness_seconds),'operation_target_start_at':start,'operation_target_end_at':end,
      'remaining_qty':remaining,'remaining_work_seconds':int(workload),'priority_reasons':reasons[:5]}

def priority_sort_key(row:dict):
    state_rank={'CRITICAL':0,'WARNING':1,'ON_TRACK':2,'WAITING':3,'DONE':4}
    return (state_rank.get(str(row.get('control_state') or ''),5),-float(row.get('dispatch_priority_score') or row.get('priority_score') or 0),
      str(row.get('po_code') or ''),int(row.get('part_sort') or 0),int(row.get('operation_sort') or 0),int(row.get('operation_id') or 0))

def dispatch_state_from_db(cur,operation_id:int)->dict:
    cur.execute('''SELECT o.*,po.status po_status,po.planned_quantity,
      src.done_qty source_done_qty,src.rework_qty source_rework_qty,
      pred.id predecessor_id,pred.status predecessor_status,pred.done_qty predecessor_done_qty,
      COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c
        WHERE c.source_operation_id=o.input_source_operation_id AND c.source_qty_kind=o.input_source_kind),0) source_consumed_qty
      FROM operations o JOIN production_orders po ON po.id=o.production_order_id
      LEFT JOIN operations src ON src.id=o.input_source_operation_id LEFT JOIN operations pred ON pred.id=o.predecessor_operation_id
      WHERE o.id=%s FOR UPDATE OF o,po''',(operation_id,));row=cur.fetchone()
    if not row:return {}
    item=dict(row);item['operation_status']=item.get('status')
    supplied=int(item.get('source_rework_qty') or 0) if str(item.get('input_source_kind') or 'GOOD').upper()=='REWORK' else int(item.get('source_done_qty') or 0)
    item['input_available_qty']=max(supplied-int(item.get('source_consumed_qty') or 0),0)
    pred={'done_qty':item.get('predecessor_done_qty'),'operation_status':item.get('predecessor_status')} if item.get('predecessor_id') else None
    return {**operation_wip(item,pred),'operation':item}
