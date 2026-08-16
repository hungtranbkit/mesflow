from __future__ import annotations

import logging
from flask import jsonify
from psycopg import DataError, IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge
from mesflow.db.repositories.base import ConflictError,NotFoundError,RepositoryError
from mesflow.domain.errors import PermissionDeniedError,ValidationError

def api_error_response(exc,*,logger_name:str=__name__):
    if isinstance(exc,RequestEntityTooLarge):
        return jsonify(ok=False,error='PAYLOAD_TOO_LARGE',message='Payload exceeds the configured limit.'),413
    if isinstance(exc,NotFoundError):
        return jsonify(ok=False,error='NOT_FOUND',message=str(exc)),404
    if isinstance(exc,(ConflictError,IntegrityError)):
        return jsonify(ok=False,error='BUSINESS_CONFLICT',message=str(exc)),409
    if isinstance(exc,PermissionDeniedError):
        # V66 domain error: not raised by any pre-existing code path today,
        # so this branch adds new behavior only for callers that opt into
        # raising it -- no existing route's status code changes.
        return jsonify(ok=False,error='FORBIDDEN',message=str(exc)),403
    if isinstance(exc,(ValueError,TypeError,DataError,RepositoryError,ValidationError)):
        return jsonify(ok=False,error='INVALID_REQUEST',message=str(exc)),400
    logging.getLogger(logger_name).exception('Unexpected API failure')
    return jsonify(ok=False,error='INTERNAL_ERROR',message='Unable to process the request.'),500
