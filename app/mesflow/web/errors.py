from __future__ import annotations

import logging
from flask import jsonify
from psycopg import DataError, IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge
from mesflow.db.repositories.base import ConflictError,NotFoundError,RepositoryError
from mesflow.domain.errors import PermissionDeniedError,ValidationError

# Constraint name -> what a user can actually do about it. Anything not listed
# still gets a Vietnamese sentence from _database_message() below; this table
# only buys a more specific one where the constraint is worth naming.
_CONSTRAINT_MESSAGES={
    'operations_code_key':'Mã Operation đã tồn tại trong hệ thống. Mỗi Operation phải có mã riêng.',
    'production_orders_code_key':'Mã Production Order đã tồn tại.',
    'templates_code_key':'Mã Template đã tồn tại.',
    'employees_employee_no_key':'Mã nhân viên đã tồn tại.',
    'stations_code_key':'Mã trạm kiosk đã tồn tại.',
    'equipment_code_key':'Mã thiết bị đã tồn tại.',
    'parts_code_key':'Mã Part đã tồn tại.',
    'sales_orders_code_key':'Mã Sales Order đã tồn tại.',
}


def _database_message(exc):
    """A Vietnamese sentence for a driver-level database error.

    The raw text of a psycopg error is written for whoever wrote the schema,
    not for the person at the workstation: a real report on TEST 2026-09-09
    was a popup reading `duplicate key value violates unique constraint
    "operations_code_key" DETAIL: Key (code)=(6126-KM-3172005-08-OP02)
    already exists.` -- which says nothing about what to do next, and leaks
    table and constraint names to the shop floor. str(exc) must therefore
    never reach the client for these; the technical text is logged instead,
    where it is actually useful.

    Business errors our own code raises deliberately (ConflictError,
    ValueError, ...) are untouched -- those messages are written for users
    and are already in Vietnamese.
    """
    constraint=getattr(getattr(exc,'diag',None),'constraint_name',None) or ''
    if constraint in _CONSTRAINT_MESSAGES:
        return _CONSTRAINT_MESSAGES[constraint]
    name=type(exc).__name__
    if name=='UniqueViolation':
        return 'Dữ liệu bị trùng với một bản ghi đã có. Kiểm tra lại mã/khóa rồi thử lại.'
    if name=='ForeignKeyViolation':
        return 'Không thực hiện được vì dữ liệu này đang được sử dụng ở nơi khác.'
    if name=='NotNullViolation':
        return 'Thiếu thông tin bắt buộc. Điền đủ các trường bắt buộc rồi thử lại.'
    if name=='CheckViolation':
        return 'Dữ liệu không hợp lệ theo quy tắc của hệ thống. Kiểm tra lại số lượng/trạng thái đã nhập.'
    if isinstance(exc,DataError):
        return 'Dữ liệu nhập không đúng định dạng. Kiểm tra lại rồi thử lại.'
    return 'Thao tác vi phạm ràng buộc dữ liệu. Kiểm tra lại thông tin rồi thử lại.'


def api_error_response(exc,*,logger_name:str=__name__):
    if isinstance(exc,RequestEntityTooLarge):
        return jsonify(ok=False,error='PAYLOAD_TOO_LARGE',message='Tệp tải lên vượt quá dung lượng cho phép.'),413
    if isinstance(exc,NotFoundError):
        return jsonify(ok=False,error='NOT_FOUND',message=str(exc)),404
    # Our own ConflictError carries a message written for the user; a psycopg
    # IntegrityError carries one written for a DBA. Split them.
    if isinstance(exc,ConflictError):
        return jsonify(ok=False,error='BUSINESS_CONFLICT',message=str(exc)),409
    if isinstance(exc,IntegrityError):
        logging.getLogger(logger_name).warning('Database constraint violation: %s',exc)
        return jsonify(ok=False,error='BUSINESS_CONFLICT',message=_database_message(exc)),409
    if isinstance(exc,PermissionDeniedError):
        # V66 domain error: not raised by any pre-existing code path today,
        # so this branch adds new behavior only for callers that opt into
        # raising it -- no existing route's status code changes.
        return jsonify(ok=False,error='FORBIDDEN',message=str(exc)),403
    if isinstance(exc,DataError):
        logging.getLogger(logger_name).warning('Database data error: %s',exc)
        return jsonify(ok=False,error='INVALID_REQUEST',message=_database_message(exc)),400
    if isinstance(exc,(ValueError,TypeError,RepositoryError,ValidationError)):
        return jsonify(ok=False,error='INVALID_REQUEST',message=str(exc)),400
    logging.getLogger(logger_name).exception('Unexpected API failure')
    return jsonify(ok=False,error='INTERNAL_ERROR',message='Hệ thống chưa xử lý được yêu cầu. Thử lại hoặc báo IT nếu vẫn lỗi.'),500
