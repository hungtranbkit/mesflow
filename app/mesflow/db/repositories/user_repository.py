from werkzeug.security import generate_password_hash
from mesflow.db.connection import transaction, fetch_one, fetch_all


class UserRepository:
    def count(self):
        return int(fetch_one('SELECT COUNT(*) AS n FROM users')['n'])

    def get_by_username(self, username):
        return fetch_one('SELECT * FROM users WHERE username=%s', (username,))

    def get_by_id(self, user_id):
        return fetch_one('SELECT * FROM users WHERE id=%s', (user_id,))

    def bump_session_epoch(self, user_id):
        """Invalidate every session cookie already issued to this user.

        Used by logout and by any administrative revocation. A password change
        invalidates sessions on its own (the hash is part of the stamp), so it
        does not need this -- but it bumps too, so a forced reset ends other
        devices even if the new password happens to hash to the same value.
        """
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE users SET session_epoch=session_epoch+1,updated_at=now() WHERE id=%s',
                            (user_id,))

    def list_all(self):
        return fetch_all('''
            SELECT id, username, display_name, role, active,
                   must_change_password, created_at, updated_at
            FROM users
            ORDER BY active DESC, role, username
        ''')

    def create(self, username, display_name, password, role='viewer', must_change=True):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO users(
                        username, display_name, password_hash, role,
                        active, must_change_password
                    ) VALUES(%s,%s,%s,%s,true,%s)
                    RETURNING id
                ''', (username, display_name, generate_password_hash(password), role, must_change))
                return cur.fetchone()['id']

    def update_profile(self, user_id, display_name, role, active):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE users
                    SET display_name=%s, role=%s, active=%s, updated_at=now()
                    WHERE id=%s RETURNING id
                ''', (display_name, role, active, user_id))
                row = cur.fetchone()
                return row['id'] if row else None

    def set_password(self, user_id, password, must_change=False):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE users
                    SET password_hash=%s, must_change_password=%s, session_epoch=session_epoch+1, updated_at=now()
                    WHERE id=%s RETURNING id
                ''', (generate_password_hash(password), must_change, user_id))
                row = cur.fetchone()
                return row['id'] if row else None

    def reset_password(self, username, password, *, activate=True, role='admin'):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO users(
                        username, display_name, password_hash, role,
                        active, must_change_password
                    ) VALUES(%s,%s,%s,%s,%s,false)
                    ON CONFLICT(username) DO UPDATE SET
                        password_hash=excluded.password_hash,
                        role=excluded.role,
                        active=excluded.active,
                        must_change_password=false,
                        updated_at=now()
                    RETURNING id
                ''', (username, 'KIMEX Administrator', generate_password_hash(password), role, activate))
                return cur.fetchone()['id']
