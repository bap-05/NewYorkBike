"""Independent one-shot Analysis job, using the existing Aiven GitHub Secrets."""
import json
import os
from pathlib import Path
import tempfile

from analysis.config import AnalysisOptions
from analysis.main import run
from shared.config import ROOT, Settings
from shared.logging_config import configure_logging
from shared.models import AnalysisResult, ServiceRun, Station, CollectionRun, BikeObservation, WeatherObservation, ObservationWeatherLink
from shared.schema import check_schema


def main():
    certificate_path = None
    try:
        if os.getenv("GITHUB_ACTIONS") != "true" or (ROOT / ".env").exists():
            raise ValueError("Use GitHub Secrets in CI; use analysis.main locally")
        required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_CA_CERT", "RUNNER_TEMP")
        missing = [name for name in required if not os.getenv(name, "").strip()]
        if missing:
            print("Missing Secrets/environment: " + ", ".join(missing))
            return 1
        if not os.getenv("STATION_IDS", "").strip():
            data = json.loads((ROOT / "config" / "citibike_stations.json").read_text(encoding="utf-8"))
            if data.get("source") != "citibike":
                raise ValueError("Station configuration must use source=citibike")
            os.environ["STATION_IDS"] = ",".join(data["station_ids"])
        # Analysis never uses outbound source APIs or proxy credentials.
        os.environ["OUTBOUND_PROXY_ENABLED"] = "false"
        os.environ["OUTBOUND_PROXY_URLS"] = "[]"
        os.environ["BIKE_SOURCE"] = "citibike"
        os.environ["DISPLAY_TIMEZONE"] = "America/New_York"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".pem",
                prefix="citibike-analysis-ca-", dir=os.environ["RUNNER_TEMP"], delete=False) as certificate:
            certificate_path = Path(certificate.name)
            certificate.write(os.environ["MYSQL_CA_CERT"])
        certificate_path.chmod(0o600)
        os.environ["MYSQL_SSL_CA"] = str(certificate_path)
        settings = Settings.load(outbound=False)
        options = AnalysisOptions.load()
        configure_logging("America/New_York")
        check_schema(settings, required_revision="0004_analysis",
                     models=(Station, CollectionRun, BikeObservation, WeatherObservation,
                             ObservationWeatherLink, ServiceRun, AnalysisResult))
        return run(settings, options, schedule=False)
    except Exception as exc:
        print(f"GitHub Analysis failed ({type(exc).__name__}). Check Secrets, TLS and migration 0004_analysis.")
        return 1
    finally:
        if certificate_path is not None:
            certificate_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
