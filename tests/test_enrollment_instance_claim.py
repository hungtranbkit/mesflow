"""Execute the actual enrollment handler with external DB calls replaced.
The PostgreSQL counterpart lives in test_kiosk_enrollment_strict_pg.py.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, jsonify, request
from mesflow.domain.errors import PermissionDeniedError


@pytest.mark.parametrize('state', ['UNVERIFIED_CLONE', 'UNVERIFIED_NO_SECRET', 'MISSING'])
def test_claim_does_not_reach_repository_on_unverified_instance(state):
    path = Path(__file__).parents[1] / 'app/mesflow/web/execution.py'
    tree = ast.parse(path.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_kiosk_enrollment_response')
    reached = []
    class Repo:
        def enrollment_contact(self, *args):
            reached.append(True)
            return 'PENDING', {'enroll_secret_hash': 'abcdef'}, None
        @staticmethod
        def enrollment_code(value):
            return value.upper()
    env = {'instance_identity': SimpleNamespace(current=lambda: {'state': state}),
           'KioskRepository': Repo, 'jsonify': jsonify, 'request': request}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), env)
    with Flask(__name__).test_request_context('/'):
        with pytest.raises(PermissionDeniedError):
            env['_kiosk_enrollment_response']({'device_uuid': 'test', 'device_secret': 'a' * 64})
    assert reached == []
