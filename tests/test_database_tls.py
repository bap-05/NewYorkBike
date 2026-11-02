"""Validate TLS policy without contacting a database or reading real credentials."""
from dataclasses import replace
import ssl
from unittest.mock import MagicMock

import certifi
import pytest

from shared.database import make_engine
from scripts import check_database


def test_ca_requires_certificate_and_hostname_verification(settings, monkeypatch):
    from shared import database
    factory = MagicMock()
    monkeypatch.setattr(database, "create_engine", factory)
    monkeypatch.setattr(database.event, "listens_for", lambda *args: lambda fn: fn)
    make_engine(replace(settings, mysql_ssl_ca=certifi.where()))
    context = factory.call_args.kwargs["connect_args"]["ssl"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_invalid_ca_fails_before_connection(settings, tmp_path):
    path = tmp_path / "invalid-ca.pem"
    path.write_text("not a certificate")
    with pytest.raises(ValueError, match="MYSQL_SSL_CA"):
        make_engine(replace(settings, mysql_ssl_ca=path))


def test_configured_ca_rejects_unencrypted_connection(settings, monkeypatch):
    from shared import database
    callbacks = []
    monkeypatch.setattr(database, "create_engine", MagicMock())
    monkeypatch.setattr(database.event, "listens_for", lambda *args: callbacks.append)
    make_engine(replace(settings, mysql_ssl_ca=certifi.where()))
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("Ssl_cipher", "")
    with pytest.raises(RuntimeError, match="TLS is required"):
        callbacks[0](connection, None)
    assert cursor.execute.call_count == 1


def test_local_mysql_does_not_require_ca(settings, monkeypatch):
    from shared import database
    factory = MagicMock()
    monkeypatch.setattr(database, "create_engine", factory)
    monkeypatch.setattr(database.event, "listens_for", lambda *args: lambda fn: fn)
    make_engine(replace(settings, mysql_ssl_ca=None))
    assert "ssl" not in factory.call_args.kwargs["connect_args"]


def test_connection_errors_never_print_secrets(monkeypatch, capsys):
    monkeypatch.setattr(check_database.Settings, "load", lambda: None)
    def fail(_):
        raise RuntimeError("secret-password-and-user")
    monkeypatch.setattr(check_database, "make_engine", fail)
    assert check_database.main() == 1
    output = capsys.readouterr().out
    assert "FAILED (RuntimeError)" in output
    assert "secret-password-and-user" not in output


def test_session_keeps_server_quoting_mode(settings, monkeypatch):
    from shared import database
    callbacks = []
    monkeypatch.setattr(database, "create_engine", MagicMock())
    monkeypatch.setattr(database.event, "listens_for", lambda *args: callbacks.append)
    make_engine(replace(settings, mysql_ssl_ca=None))
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("ANSI_QUOTES,NO_BACKSLASH_ESCAPES",)
    callbacks[0](connection, None)
    query, parameters = cursor.execute.call_args.args
    assert query == "SET SESSION sql_mode = %s"
    modes = set(parameters[0].split(","))
    assert {"ANSI_QUOTES", "NO_BACKSLASH_ESCAPES", "STRICT_TRANS_TABLES"} <= modes
