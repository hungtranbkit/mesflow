"""Unit tests for `mesflow.cli.reset_password` -- the emergency, server-CLI
password reset added for the Bootstrap deployment guide's "Khôi phục truy
cập / Quên mật khẩu" section.

Fully isolated: no real PostgreSQL, no real container. `UserRepository`
and `AuditRepository` are mocked, so nothing here can touch DEV/Production
Test/Production data. This intentionally does NOT cover
`mesflow.db.repositories.user_repository.UserRepository.set_password`'s
own SQL (that's pre-existing code already exercised by
`mesflow.web.users.reset_user_password`, which uses the exact same
repository method) -- these tests cover only the NEW CLI wiring: username
lookup/validation, password policy, confirmation matching, which
repository method gets called (set_password, never the upsert
reset_password()), the audit action name, and that the password is never
printed.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from mesflow import cli


def _run(argv, user_row, getpass_values, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", argv)
    fake_repo = MagicMock()
    fake_repo.get_by_username.return_value = user_row
    fake_audit = MagicMock()
    with patch.object(cli, "UserRepository", return_value=fake_repo), \
         patch("mesflow.db.repositories.analytics.AuditRepository", return_value=fake_audit), \
         patch("getpass.getpass", side_effect=getpass_values):
        cli.reset_password()
    out = capsys.readouterr().out
    return fake_repo, fake_audit, out


class TestResetPasswordCLI:
    def test_usage_error_when_username_missing(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["mesflow.cli", "reset-password"])
        with pytest.raises(SystemExit, match="usage: python -m mesflow.cli reset-password"):
            cli.reset_password()

    def test_unknown_username_is_refused_not_created(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["mesflow.cli", "reset-password", "ghost"])
        fake_repo = MagicMock()
        fake_repo.get_by_username.return_value = None
        with patch.object(cli, "UserRepository", return_value=fake_repo):
            with pytest.raises(SystemExit, match="no user 'ghost' exists"):
                cli.reset_password()
        fake_repo.create.assert_not_called()
        fake_repo.set_password.assert_not_called()

    def test_short_password_rejected(self, monkeypatch, capsys):
        user = {"id": 7, "username": "manager1", "role": "manager"}
        with pytest.raises(SystemExit, match="at least 8 characters"):
            _run(["mesflow.cli", "reset-password", "manager1"], user, ["short1"], monkeypatch, capsys)

    def test_password_without_digit_rejected(self, monkeypatch, capsys):
        user = {"id": 7, "username": "manager1", "role": "manager"}
        with pytest.raises(SystemExit, match="letter and a digit"):
            _run(["mesflow.cli", "reset-password", "manager1"], user, ["onlyletters"], monkeypatch, capsys)

    def test_mismatched_confirmation_rejected(self, monkeypatch, capsys):
        user = {"id": 7, "username": "manager1", "role": "manager"}
        with pytest.raises(SystemExit, match="do not match"):
            _run(["mesflow.cli", "reset-password", "manager1"], user,
                 ["goodpass1", "different1"], monkeypatch, capsys)

    def test_successful_reset_preserves_role_and_uses_set_password_not_upsert(self, monkeypatch, capsys):
        user = {"id": 42, "username": "supervisor1", "role": "supervisor", "active": True}
        repo, audit, out = _run(
            ["mesflow.cli", "reset-password", "supervisor1"], user,
            ["newpass123", "newpass123"], monkeypatch, capsys,
        )
        # The only mutation is set_password -- role/active/display_name untouched.
        repo.set_password.assert_called_once_with(42, "newpass123", must_change=False)
        repo.update_profile.assert_not_called()
        repo.reset_password.assert_not_called()  # the upsert/force-role='admin' method
        repo.create.assert_not_called()
        # Audit event recorded with the exact action name the task specifies.
        audit.log.assert_called_once()
        call_args = audit.log.call_args
        assert call_args.args[0] == "cli:reset-password"
        assert call_args.args[1] == "ADMIN_PASSWORD_RESET"
        assert call_args.args[2] == "user"
        assert call_args.args[3] == "42"
        assert call_args.args[4] == {"target_username": "supervisor1", "source": "server_cli"}
        # Confirms role is echoed back unchanged and the password is never printed.
        assert "role='supervisor' unchanged" in out
        assert "newpass123" not in out

    def test_password_never_appears_in_stdout_on_failure_paths_either(self, monkeypatch, capsys):
        user = {"id": 1, "username": "admin", "role": "admin"}
        with pytest.raises(SystemExit):
            _run(["mesflow.cli", "reset-password", "admin"], user,
                 ["s3cr3tpw1", "different2"], monkeypatch, capsys)
        out = capsys.readouterr().out
        assert "s3cr3tpw1" not in out
        assert "different2" not in out
