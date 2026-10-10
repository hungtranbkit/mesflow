"""Private current-role check, separate from snapshot freshness.

The MES backend validates the signed session; this check rejects its stale role
claim after a downgrade. SELECT is granted on four users columns only, never
passwords, names, usernames or session credentials. No business data is served.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
import re
import threading


def read_scope(user_id):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row,
                         connect_timeout=2, options='-c default_transaction_read_only=on -c statement_timeout=1500 -c lock_timeout=500') as conn:
        row = conn.execute('SELECT id,role,active,must_change_password FROM users WHERE id=%s', (user_id,)).fetchone()
        conn.rollback()
        return row


class ScopeHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, *_args):
        pass  # Never log user IDs or the private service credential.

    def do_GET(self):
        supplied = self.headers.get('Authorization', '')
        expected = 'Bearer ' + os.environ['REPORT_SCOPE_KEY']
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            self.send_error(403)
            return
        match = re.fullmatch(r'/scope/([1-9][0-9]{0,9})', self.path)
        if not match:
            self.send_error(404)
            return
        try:
            value = read_scope(int(match[1]))
            payload = json.dumps({'scope': value}).encode()
        except Exception:
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_scope_server():
    if len(os.environ.get('REPORT_SCOPE_KEY', '')) < 32:
        raise RuntimeError('A private scope credential is required')
    # One request at a time plus one background batch: <=2 DB connections.
    server = HTTPServer(('0.0.0.0', 8090), ScopeHandler)
    server.timeout = 3
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
