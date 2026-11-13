"""Prediction CLI and separate explicit training command; never source API calls."""
import argparse
from datetime import timedelta
import json
import logging
from pathlib import Path
import time

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from prediction.config import PredictionOptions
from prediction.data import load_history
from prediction.learning import build_report
from prediction.registry import active_model
from prediction.training import train_once
from prediction.worker import forecast_rows, predict_once
from shared.config import Settings
from shared.database import make_engine, service_session
from shared.logging_config import configure_logging
from shared.models import ModelVersion, Prediction, ServiceRun, TrainingJob
from shared.schema import check_schema
from shared.time import display_time, sampling_slot, utcnow

logger = logging.getLogger("prediction")


def preview(settings,options,*,output="artifacts/prediction_preview.json"):
    cutoff = utcnow()
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "mysql":
                connection.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            with Session(bind=connection) as session:
                stations,groups = load_history(session,settings,cutoff,options)
                model = active_model(session,settings.bike_source,cutoff,settings,options) if inspect(connection).has_table(ModelVersion.__tablename__) else None
                forecasts = forecast_rows(stations,groups,settings,options,cutoff,model)
                evaluation,_ = build_report(stations,groups,settings,options)
                report = {"database_written":False,"preview_cutoff":cutoff.isoformat(),"configuration":options.as_dict(),
                    "forecast_preview":forecasts,"historical_evaluation":evaluation,
                    "note":"Read-only preview. No model activation, forecast publication or historical issuance."}
                target = Path(output).resolve()
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(json.dumps(report,indent=2,ensure_ascii=True,default=str)+"\n",encoding="utf-8")
                logger.info("Prediction preview: stations=%s baseline_examples=%s complete_ml=%s training_status=%s output=%s",
                    len(stations),evaluation["baseline_examples"],evaluation["complete_ml_examples"],evaluation["status"],target)
                logger.info("No database writes; training reasons=%s",evaluation["readiness_reasons"])
        return 0
    finally:
        engine.dispose()


def run(settings,options,*,schedule=False,training=False):
    engine = make_engine(settings)
    try:
        while True:
            code = 0
            try:
                with service_session(engine,"training" if training else "prediction") as session:
                    result = train_once(session,settings,options) if training else predict_once(session,settings,options)
                    logger.info("%s_run=%s status=%s summary=%s","training" if training else "prediction",result.id,result.status,
                        {"model_version_id":result.model_version_id,"readiness_reasons":result.summary.get("readiness_reasons")} if training else result.summary)
            except Exception as exc:
                logger.error("%s failed (%s). Check migration 0006_prediction and worker history.","Training" if training else "Prediction",type(exc).__name__)
                code = 1
            if not schedule:
                return code
            target = sampling_slot(utcnow())+timedelta(minutes=5)
            logger.info("Next prediction=%s [America/New_York]",display_time(target))
            while (remaining := (target-utcnow()).total_seconds()) > 0:
                time.sleep(min(remaining,30))
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Independent +30 minute forecasts; training is explicitly separate")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview",action="store_true",help="Read-only live preview and historical temporal evaluation")
    mode.add_argument("--once",action="store_true",help="Publish one five-minute prediction period; evaluate matured forecasts")
    mode.add_argument("--schedule",action="store_true",help="Predict now, then at five-minute UTC boundaries; never trains")
    mode.add_argument("--train",action="store_true",help="One explicit independent training job with temporal validation/test")
    parser.add_argument("--output",default="artifacts/prediction_preview.json")
    args = parser.parse_args()
    configure_logging("America/New_York")
    try:
        settings,options = Settings.load(outbound=False),PredictionOptions.load()
        if args.preview:
            return preview(settings,options,output=args.output)
        check_schema(settings,required_revision="0006_prediction",models=(ServiceRun,ModelVersion,TrainingJob,Prediction))
        return run(settings,options,schedule=args.schedule,training=args.train)
    except KeyboardInterrupt:
        logger.info("Prediction stopped")
        return 130
    except Exception as exc:
        logger.error("Prediction startup failed (%s). Check MySQL, configuration and migration 0006_prediction.",type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
