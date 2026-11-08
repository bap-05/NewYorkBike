"""Add prediction registry, separate training jobs and immutable issued forecasts.

Frozen dialect-specific DDL; no existing tables or observations are altered.
"""
from alembic import op

revision = "0006_prediction"
down_revision = "0005_clustering"
branch_labels = None
depends_on = None

DDL = {'mysql': ['CREATE TABLE model_versions (\n'
           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
           '\tsource VARCHAR(32) NOT NULL, \n'
           '\tname VARCHAR(128) NOT NULL, \n'
           '\tkind VARCHAR(32) NOT NULL, \n'
           '\tidentity_hash VARCHAR(64) NOT NULL, \n'
           '\tcreated_at DATETIME(6) NOT NULL, \n'
           '\ttrained_at DATETIME(6), \n'
           '\ttrain_start DATETIME(6), \n'
           '\ttrain_end DATETIME(6), \n'
           '\tfeature_config JSON NOT NULL, \n'
           '\tmetrics JSON NOT NULL, \n'
           '\tartifact JSON NOT NULL, \n'
           '\tis_active BOOL NOT NULL, \n'
           '\tPRIMARY KEY (id), \n'
           '\tCONSTRAINT uq_model_source_id UNIQUE (source, id), \n'
           '\tCONSTRAINT uq_model_identity UNIQUE (source, identity_hash), \n'
           "\tCONSTRAINT ck_model_kind CHECK (kind IN ('persistence','random_forest'))\n"
           ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin',
           'CREATE TABLE training_jobs (\n'
           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
           '\tsource VARCHAR(32) NOT NULL, \n'
           '\trequested_at DATETIME(6) NOT NULL, \n'
           '\tstarted_at DATETIME(6) NOT NULL, \n'
           '\tfinished_at DATETIME(6), \n'
           '\tstatus VARCHAR(24) NOT NULL, \n'
           '\tparameters JSON NOT NULL, \n'
           '\tsummary JSON, \n'
           '\tmodel_version_id INTEGER, \n'
           '\terror_summary VARCHAR(255), \n'
           '\tPRIMARY KEY (id), \n'
           '\tCONSTRAINT fk_training_model FOREIGN KEY(source, model_version_id) REFERENCES model_versions '
           '(source, id) ON DELETE RESTRICT, \n'
           '\tCONSTRAINT ck_training_status CHECK (status IN '
           "('running','success','insufficient_data','baseline_preferred','failed'))\n"
           ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin',
           'CREATE TABLE predictions (\n'
           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
           '\tsource VARCHAR(32) NOT NULL, \n'
           '\tstation_id VARCHAR(128) NOT NULL, \n'
           '\tservice_run_id INTEGER NOT NULL, \n'
           '\tscheduled_at DATETIME(6) NOT NULL, \n'
           '\tinput_cutoff_at DATETIME(6) NOT NULL, \n'
           '\tinput_time DATETIME(6), \n'
           '\ttarget_at DATETIME(6), \n'
           '\tissued_at DATETIME(6) NOT NULL, \n'
           '\tinput_observation_id INTEGER, \n'
           '\tmodel_version_id INTEGER, \n'
           '\tstatus VARCHAR(24) NOT NULL, \n'
           '\treason VARCHAR(128), \n'
           '\traw_predicted_bikes DOUBLE, \n'
           '\tpredicted_bikes DOUBLE, \n'
           '\tfeatures JSON NOT NULL, \n'
           '\tactual_observation_id INTEGER, \n'
           '\tevaluated_at DATETIME(6), \n'
           '\tactual_bikes INTEGER, \n'
           '\tactual_time DATETIME(6), \n'
           '\ttarget_offset_seconds DOUBLE, \n'
           '\tabsolute_error DOUBLE, \n'
           '\tsquared_error DOUBLE, \n'
           '\tserved_absolute_error DOUBLE, \n'
           '\tPRIMARY KEY (id), \n'
           '\tCONSTRAINT uq_prediction_service_station UNIQUE (source, station_id, service_run_id), \n'
           '\tCONSTRAINT fk_prediction_station FOREIGN KEY(source, station_id) REFERENCES stations (source, '
           'station_id) ON DELETE RESTRICT, \n'
           '\tCONSTRAINT fk_prediction_service FOREIGN KEY(source, service_run_id) REFERENCES service_runs '
           '(source, id) ON DELETE RESTRICT, \n'
           '\tCONSTRAINT fk_prediction_model FOREIGN KEY(source, model_version_id) REFERENCES model_versions '
           '(source, id) ON DELETE RESTRICT, \n'
           "\tCONSTRAINT ck_prediction_status CHECK (status IN ('baseline','ml','unavailable')), \n"
           '\tCONSTRAINT ck_prediction_nonnegative CHECK (predicted_bikes IS NULL OR predicted_bikes >= '
           '0), \n'
           "\tCONSTRAINT ck_prediction_publication CHECK ((status='unavailable' AND predicted_bikes IS NULL "
           "AND raw_predicted_bikes IS NULL) OR (status IN ('baseline','ml') AND predicted_bikes IS NOT NULL "
           'AND raw_predicted_bikes IS NOT NULL AND model_version_id IS NOT NULL AND input_observation_id IS '
           'NOT NULL AND input_time IS NOT NULL AND target_at IS NOT NULL AND target_at > issued_at)), \n'
           '\tFOREIGN KEY(input_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT, \n'
           '\tFOREIGN KEY(actual_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT\n'
           ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin',
           'CREATE INDEX ix_prediction_station_target ON predictions (source, station_id, target_at)'],
 'sqlite': ['CREATE TABLE model_versions (\n'
            '\tid INTEGER NOT NULL, \n'
            '\tsource VARCHAR(32) NOT NULL, \n'
            '\tname VARCHAR(128) NOT NULL, \n'
            '\tkind VARCHAR(32) NOT NULL, \n'
            '\tidentity_hash VARCHAR(64) NOT NULL, \n'
            '\tcreated_at DATETIME NOT NULL, \n'
            '\ttrained_at DATETIME, \n'
            '\ttrain_start DATETIME, \n'
            '\ttrain_end DATETIME, \n'
            '\tfeature_config JSON NOT NULL, \n'
            '\tmetrics JSON NOT NULL, \n'
            '\tartifact JSON NOT NULL, \n'
            '\tis_active BOOLEAN NOT NULL, \n'
            '\tPRIMARY KEY (id), \n'
            '\tCONSTRAINT uq_model_source_id UNIQUE (source, id), \n'
            '\tCONSTRAINT uq_model_identity UNIQUE (source, identity_hash), \n'
            "\tCONSTRAINT ck_model_kind CHECK (kind IN ('persistence','random_forest'))\n"
            ')',
            'CREATE TABLE training_jobs (\n'
            '\tid INTEGER NOT NULL, \n'
            '\tsource VARCHAR(32) NOT NULL, \n'
            '\trequested_at DATETIME NOT NULL, \n'
            '\tstarted_at DATETIME NOT NULL, \n'
            '\tfinished_at DATETIME, \n'
            '\tstatus VARCHAR(24) NOT NULL, \n'
            '\tparameters JSON NOT NULL, \n'
            '\tsummary JSON, \n'
            '\tmodel_version_id INTEGER, \n'
            '\terror_summary VARCHAR(255), \n'
            '\tPRIMARY KEY (id), \n'
            '\tCONSTRAINT fk_training_model FOREIGN KEY(source, model_version_id) REFERENCES model_versions '
            '(source, id) ON DELETE RESTRICT, \n'
            '\tCONSTRAINT ck_training_status CHECK (status IN '
            "('running','success','insufficient_data','baseline_preferred','failed'))\n"
            ')',
            'CREATE TABLE predictions (\n'
            '\tid INTEGER NOT NULL, \n'
            '\tsource VARCHAR(32) NOT NULL, \n'
            '\tstation_id VARCHAR(128) NOT NULL, \n'
            '\tservice_run_id INTEGER NOT NULL, \n'
            '\tscheduled_at DATETIME NOT NULL, \n'
            '\tinput_cutoff_at DATETIME NOT NULL, \n'
            '\tinput_time DATETIME, \n'
            '\ttarget_at DATETIME, \n'
            '\tissued_at DATETIME NOT NULL, \n'
            '\tinput_observation_id INTEGER, \n'
            '\tmodel_version_id INTEGER, \n'
            '\tstatus VARCHAR(24) NOT NULL, \n'
            '\treason VARCHAR(128), \n'
            '\traw_predicted_bikes DOUBLE, \n'
            '\tpredicted_bikes DOUBLE, \n'
            '\tfeatures JSON NOT NULL, \n'
            '\tactual_observation_id INTEGER, \n'
            '\tevaluated_at DATETIME, \n'
            '\tactual_bikes INTEGER, \n'
            '\tactual_time DATETIME, \n'
            '\ttarget_offset_seconds DOUBLE, \n'
            '\tabsolute_error DOUBLE, \n'
            '\tsquared_error DOUBLE, \n'
            '\tserved_absolute_error DOUBLE, \n'
            '\tPRIMARY KEY (id), \n'
            '\tCONSTRAINT uq_prediction_service_station UNIQUE (source, station_id, service_run_id), \n'
            '\tCONSTRAINT fk_prediction_station FOREIGN KEY(source, station_id) REFERENCES stations (source, '
            'station_id) ON DELETE RESTRICT, \n'
            '\tCONSTRAINT fk_prediction_service FOREIGN KEY(source, service_run_id) REFERENCES service_runs '
            '(source, id) ON DELETE RESTRICT, \n'
            '\tCONSTRAINT fk_prediction_model FOREIGN KEY(source, model_version_id) REFERENCES '
            'model_versions (source, id) ON DELETE RESTRICT, \n'
            "\tCONSTRAINT ck_prediction_status CHECK (status IN ('baseline','ml','unavailable')), \n"
            '\tCONSTRAINT ck_prediction_nonnegative CHECK (predicted_bikes IS NULL OR predicted_bikes >= '
            '0), \n'
            "\tCONSTRAINT ck_prediction_publication CHECK ((status='unavailable' AND predicted_bikes IS NULL "
            "AND raw_predicted_bikes IS NULL) OR (status IN ('baseline','ml') AND predicted_bikes IS NOT "
            'NULL AND raw_predicted_bikes IS NOT NULL AND model_version_id IS NOT NULL AND '
            'input_observation_id IS NOT NULL AND input_time IS NOT NULL AND target_at IS NOT NULL AND '
            'target_at > issued_at)), \n'
            '\tFOREIGN KEY(input_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT, \n'
            '\tFOREIGN KEY(actual_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT\n'
            ')',
            'CREATE INDEX ix_prediction_station_target ON predictions (source, station_id, target_at)']}


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect not in DDL:
        raise RuntimeError("Prediction migration supports MySQL; SQLite is for isolated tests")
    for statement in DDL[dialect]:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Forward-only: retain models, training jobs and issued forecasts")
