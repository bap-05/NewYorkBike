"""CI orchestration with test-only settings; no real database or network calls."""
from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import run_github_collection as ci


@pytest.fixture
def cloud(tmp_path, monkeypatch, settings):
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "citibike_stations.json").write_text(json.dumps({
        "source": "citibike", "station_ids": ["UNIT-TEST-A", "UNIT-TEST-B"]}))
    for name, value in {"GITHUB_ACTIONS": "true", "RUNNER_TEMP": str(tmp_path),
                        "MYSQL_HOST": "db.test.invalid", "MYSQL_PORT": "3306",
                        "MYSQL_DATABASE": "unit_test", "MYSQL_USER": "unit_test",
                        "MYSQL_PASSWORD": "test-only-secret", "MYSQL_CA_CERT": "test-only-ca",
                        "STATION_IDS": ""}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(ci.Settings, "load", lambda: replace(settings,
        station_ids=tuple(os.environ["STATION_IDS"].split(","))))
    monkeypatch.setattr(ci, "configure_logging", lambda *args: None)
    monkeypatch.setattr(ci, "check_migration", MagicMock())
    monkeypatch.setattr(ci, "run", MagicMock(return_value=0))
    return tmp_path


def summary(root):
    return json.loads((root / "data/bronze/github_collection.json").read_text())


def test_default_and_override_station_ids(cloud, monkeypatch):
    assert ci.station_ids() == ("UNIT-TEST-A", "UNIT-TEST-B")
    monkeypatch.setenv("STATION_IDS", "OVERRIDE-A, OVERRIDE-B")
    assert ci.station_ids() == ("OVERRIDE-A", "OVERRIDE-B")


@pytest.mark.parametrize("value", ["DUPLICATE,DUPLICATE", "A,,B", "A," ])
def test_invalid_selection_prevents_collection(cloud, monkeypatch, value):
    monkeypatch.setenv("STATION_IDS", value)
    assert ci.main() == 1
    ci.run.assert_not_called()


def test_one_run_tls_temp_file_removed_and_summary_written(cloud, monkeypatch):
    def collect(settings, *, schedule):
        assert schedule is False
        assert len(settings.station_ids) == 2
        assert Path(os.environ["MYSQL_SSL_CA"]).read_text() == "test-only-ca"
        return 0
    monkeypatch.setattr(ci, "run", collect)
    assert ci.main() == 0
    assert not Path(os.environ["MYSQL_SSL_CA"]).exists()
    assert summary(cloud)["collector_started"] is True
    assert summary(cloud)["exit_code"] == 0


def test_failed_collection_preserves_raw_and_error_exit(cloud, monkeypatch):
    def collect(*args, **kwargs):
        folder = cloud / "data/bronze/citibike/test-only/attempt-1"
        folder.mkdir(parents=True)
        (folder / "response.body").write_bytes(b"unit-test-only-response")
        (folder / "manifest.json").write_text("{}")
        return 1
    monkeypatch.setattr(ci, "run", collect)
    assert ci.main() == 1
    assert len(summary(cloud)["manifests"]) == 1
    assert (cloud / "data/bronze/citibike/test-only/attempt-1/response.body").exists()


def test_migration_failure_does_not_collect_or_leak_error(cloud, monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError("test-only-secret-connection-uri")
    monkeypatch.setattr(ci, "check_migration", fail)
    assert ci.main() == 1
    ci.run.assert_not_called()
    assert summary(cloud)["collector_started"] is False
    assert "test-only-secret" not in capsys.readouterr().out
    assert not Path(os.environ["MYSQL_SSL_CA"]).exists()


def test_missing_secret_fails_before_database_or_network(cloud, monkeypatch, capsys):
    monkeypatch.delenv("MYSQL_PASSWORD")
    assert ci.main() == 1
    ci.check_migration.assert_not_called()
    ci.run.assert_not_called()
    assert "MYSQL_PASSWORD" in capsys.readouterr().out


def test_ci_refuses_checked_in_dotenv(cloud):
    (cloud / ".env").write_text("unit-test-only")
    assert ci.main() == 1
    ci.check_migration.assert_not_called()
    ci.run.assert_not_called()
