CREATE TABLE collection_runs (
	id INTEGER NOT NULL, 
	scheduled_at DATETIME NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	source VARCHAR(64) NOT NULL, 
	feed_metadata JSON, 
	bronze_manifest_path VARCHAR(1024), 
	status VARCHAR(16) NOT NULL, 
	success_count INTEGER NOT NULL, 
	error_count INTEGER NOT NULL, 
	attempt_count INTEGER NOT NULL, 
	error_summary TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_run_source_sample UNIQUE (source, scheduled_at), 
	CONSTRAINT ck_run_status CHECK (status IN ('running','success','partial','failed'))
);

CREATE TABLE model_versions (
	id INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	identity_hash VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	trained_at DATETIME, 
	train_start DATETIME, 
	train_end DATETIME, 
	feature_config JSON NOT NULL, 
	metrics JSON NOT NULL, 
	artifact JSON NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_model_source_id UNIQUE (source, id), 
	CONSTRAINT uq_model_identity UNIQUE (source, identity_hash), 
	CONSTRAINT ck_model_kind CHECK (kind IN ('persistence','random_forest'))
);

CREATE TABLE service_runs (
	id INTEGER NOT NULL, 
	service_name VARCHAR(32) NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	scheduled_at DATETIME NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	heartbeat_at DATETIME NOT NULL, 
	input_watermark DATETIME, 
	status VARCHAR(16) NOT NULL, 
	attempt_count INTEGER NOT NULL, 
	calculation_version VARCHAR(32) NOT NULL, 
	configuration_hash VARCHAR(64) NOT NULL, 
	configuration JSON NOT NULL, 
	summary JSON, 
	result_count INTEGER NOT NULL, 
	error_summary VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_service_source_id UNIQUE (source, id), 
	CONSTRAINT uq_service_period_config UNIQUE (service_name, source, scheduled_at, calculation_version, configuration_hash), 
	CONSTRAINT ck_service_status CHECK (status IN ('running','success','skipped','failed')), 
	CONSTRAINT ck_service_counts CHECK (attempt_count >= 1 AND result_count >= 0)
);

CREATE INDEX ix_service_latest ON service_runs (service_name, source, scheduled_at);

CREATE TABLE stations (
	source VARCHAR(32) DEFAULT 'seoul' NOT NULL, 
	station_id VARCHAR(128) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	latitude NUMERIC(10, 6) NOT NULL, 
	longitude NUMERIC(10, 6) NOT NULL, 
	rack_count INTEGER, 
	capacity INTEGER, 
	information_updated_at DATETIME, 
	is_monitored BOOLEAN NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (source, station_id), 
	CONSTRAINT ck_station_racks CHECK (rack_count IS NULL OR rack_count >= 0), 
	CONSTRAINT ck_station_capacity CHECK (capacity IS NULL OR capacity >= 0), 
	CONSTRAINT ck_station_latitude CHECK (latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_station_longitude CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE analysis_results (
	id INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	station_id VARCHAR(128) NOT NULL, 
	window_start DATETIME NOT NULL, 
	window_end DATETIME NOT NULL, 
	aggregation VARCHAR(16) NOT NULL, 
	metric_name VARCHAR(64) NOT NULL, 
	metric_value DOUBLE, 
	sample_count INTEGER NOT NULL, 
	observed_sample_count INTEGER NOT NULL, 
	expected_sample_count INTEGER NOT NULL, 
	coverage DOUBLE, 
	quality_status VARCHAR(24) NOT NULL, 
	dimensions JSON NOT NULL, 
	input_cutoff DATETIME NOT NULL, 
	input_watermark DATETIME, 
	calculated_at DATETIME NOT NULL, 
	calculation_version VARCHAR(32) NOT NULL, 
	configuration_hash VARCHAR(64) NOT NULL, 
	service_run_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_analysis_station FOREIGN KEY(source, station_id) REFERENCES stations (source, station_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_analysis_service FOREIGN KEY(source, service_run_id) REFERENCES service_runs (source, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_analysis_window_metric UNIQUE (source, station_id, window_start, window_end, aggregation, metric_name, calculation_version, configuration_hash), 
	CONSTRAINT ck_analysis_window CHECK (window_end > window_start), 
	CONSTRAINT ck_analysis_aggregation CHECK (aggregation IN ('hour','day')), 
	CONSTRAINT ck_analysis_counts CHECK (sample_count >= 0 AND observed_sample_count >= 0 AND expected_sample_count >= 0), 
	CONSTRAINT ck_analysis_coverage CHECK (coverage IS NULL OR (coverage >= 0 AND coverage <= 1)), 
	CONSTRAINT ck_analysis_quality CHECK (quality_status IN ('ok','low_coverage','insufficient_data'))
);

CREATE INDEX ix_analysis_station_window ON analysis_results (source, station_id, window_start);

CREATE TABLE bike_observations (
	id INTEGER NOT NULL, 
	source VARCHAR(32) DEFAULT 'seoul' NOT NULL, 
	station_id VARCHAR(128) NOT NULL, 
	collection_run_id INTEGER NOT NULL, 
	sampled_at DATETIME NOT NULL, 
	collected_at DATETIME NOT NULL, 
	source_observed_at DATETIME, 
	available_bikes INTEGER, 
	available_docks INTEGER, 
	is_installed BOOLEAN, 
	is_renting BOOLEAN, 
	is_returning BOOLEAN, 
	feed_last_updated DATETIME, 
	gbfs_version VARCHAR(8), 
	quality_status VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_bike_source_station FOREIGN KEY(source, station_id) REFERENCES stations (source, station_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_bike_source_station_sample UNIQUE (source, station_id, sampled_at), 
	CONSTRAINT ck_bike_count CHECK (available_bikes IS NULL OR available_bikes >= 0), 
	CONSTRAINT ck_bike_docks CHECK (available_docks IS NULL OR available_docks >= 0), 
	CONSTRAINT ck_bike_quality CHECK (quality_status IN ('valid','missing','invalid','inactive','stale')), 
	FOREIGN KEY(collection_run_id) REFERENCES collection_runs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_bike_run ON bike_observations (collection_run_id);

CREATE INDEX ix_bike_source_station_time ON bike_observations (source, station_id, collected_at);

CREATE INDEX ix_bike_station_collected ON bike_observations (station_id, collected_at);

CREATE TABLE clustering_runs (
	id INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	run_date DATE NOT NULL, 
	service_run_id INTEGER NOT NULL, 
	window_start DATETIME NOT NULL, 
	window_end DATETIME NOT NULL, 
	input_cutoff DATETIME NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(24) NOT NULL, 
	algorithm VARCHAR(64) NOT NULL, 
	calculation_version VARCHAR(32) NOT NULL, 
	configuration_hash VARCHAR(64) NOT NULL, 
	feature_config JSON NOT NULL, 
	parameters JSON, 
	summary JSON, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_clustering_source_id UNIQUE (source, id), 
	CONSTRAINT uq_clustering_day_config UNIQUE (source, run_date, calculation_version, configuration_hash), 
	CONSTRAINT fk_clustering_service FOREIGN KEY(source, service_run_id) REFERENCES service_runs (source, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_clustering_window CHECK (window_end > window_start AND input_cutoff >= window_end), 
	CONSTRAINT ck_clustering_status CHECK (status IN ('running','success','insufficient_data','failed'))
);

CREATE INDEX ix_clustering_latest ON clustering_runs (source, run_date, status);

CREATE TABLE training_jobs (
	id INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	requested_at DATETIME NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(24) NOT NULL, 
	parameters JSON NOT NULL, 
	summary JSON, 
	model_version_id INTEGER, 
	error_summary VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_training_model FOREIGN KEY(source, model_version_id) REFERENCES model_versions (source, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_training_status CHECK (status IN ('running','success','insufficient_data','baseline_preferred','failed'))
);

CREATE TABLE weather_observations (
	id INTEGER NOT NULL, 
	collection_run_id INTEGER, 
	requested_latitude NUMERIC(10, 6) NOT NULL, 
	requested_longitude NUMERIC(10, 6) NOT NULL, 
	returned_latitude NUMERIC(10, 6), 
	returned_longitude NUMERIC(10, 6), 
	weather_time DATETIME NOT NULL, 
	collected_at DATETIME NOT NULL, 
	temperature FLOAT, 
	humidity FLOAT, 
	rain FLOAT, 
	wind_speed FLOAT, 
	units JSON NOT NULL, 
	temperature_unit VARCHAR(20), 
	humidity_unit VARCHAR(20), 
	rain_unit VARCHAR(20), 
	wind_speed_unit VARCHAR(20), 
	interval_seconds INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_weather_location_time_source UNIQUE (requested_latitude, requested_longitude, weather_time, source), 
	CONSTRAINT ck_weather_humidity CHECK (humidity IS NULL OR humidity BETWEEN 0 AND 100), 
	CONSTRAINT ck_weather_rain CHECK (rain IS NULL OR rain >= 0), 
	CONSTRAINT ck_weather_wind CHECK (wind_speed IS NULL OR wind_speed >= 0), 
	CONSTRAINT ck_weather_interval CHECK (interval_seconds > 0), 
	FOREIGN KEY(collection_run_id) REFERENCES collection_runs (id) ON DELETE RESTRICT
);

CREATE TABLE observation_weather_links (
	bike_observation_id INTEGER NOT NULL, 
	weather_observation_id INTEGER NOT NULL, 
	PRIMARY KEY (bike_observation_id), 
	FOREIGN KEY(bike_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(weather_observation_id) REFERENCES weather_observations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_observation_weather_links_weather_observation_id ON observation_weather_links (weather_observation_id);

CREATE TABLE predictions (
	id INTEGER NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	station_id VARCHAR(128) NOT NULL, 
	service_run_id INTEGER NOT NULL, 
	scheduled_at DATETIME NOT NULL, 
	input_cutoff_at DATETIME NOT NULL, 
	input_time DATETIME, 
	target_at DATETIME, 
	issued_at DATETIME NOT NULL, 
	input_observation_id INTEGER, 
	model_version_id INTEGER, 
	status VARCHAR(24) NOT NULL, 
	reason VARCHAR(128), 
	raw_predicted_bikes DOUBLE, 
	predicted_bikes DOUBLE, 
	features JSON NOT NULL, 
	actual_observation_id INTEGER, 
	evaluated_at DATETIME, 
	actual_bikes INTEGER, 
	actual_time DATETIME, 
	target_offset_seconds DOUBLE, 
	absolute_error DOUBLE, 
	squared_error DOUBLE, 
	served_absolute_error DOUBLE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_prediction_service_station UNIQUE (source, station_id, service_run_id), 
	CONSTRAINT fk_prediction_station FOREIGN KEY(source, station_id) REFERENCES stations (source, station_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_prediction_service FOREIGN KEY(source, service_run_id) REFERENCES service_runs (source, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_prediction_model FOREIGN KEY(source, model_version_id) REFERENCES model_versions (source, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_prediction_status CHECK (status IN ('baseline','ml','unavailable')), 
	CONSTRAINT ck_prediction_nonnegative CHECK (predicted_bikes IS NULL OR predicted_bikes >= 0), 
	CONSTRAINT ck_prediction_publication CHECK ((status='unavailable' AND predicted_bikes IS NULL AND raw_predicted_bikes IS NULL) OR (status IN ('baseline','ml') AND predicted_bikes IS NOT NULL AND raw_predicted_bikes IS NOT NULL AND model_version_id IS NOT NULL AND input_observation_id IS NOT NULL AND input_time IS NOT NULL AND target_at IS NOT NULL AND target_at > issued_at)), 
	FOREIGN KEY(input_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(actual_observation_id) REFERENCES bike_observations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_prediction_station_target ON predictions (source, station_id, target_at);

CREATE TABLE station_clusters (
	source VARCHAR(32) NOT NULL, 
	clustering_run_id INTEGER NOT NULL, 
	station_id VARCHAR(128) NOT NULL, 
	cluster_label INTEGER NOT NULL, 
	distance_to_centroid DOUBLE NOT NULL, 
	feature_values JSON NOT NULL, 
	metadata_snapshot JSON NOT NULL, 
	sample_count INTEGER NOT NULL, 
	expected_sample_count INTEGER NOT NULL, 
	coverage DOUBLE NOT NULL, 
	profile JSON NOT NULL, 
	PRIMARY KEY (source, clustering_run_id, station_id), 
	CONSTRAINT fk_cluster_station FOREIGN KEY(source, station_id) REFERENCES stations (source, station_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cluster_run FOREIGN KEY(source, clustering_run_id) REFERENCES clustering_runs (source, id) ON DELETE RESTRICT, 
	CONSTRAINT ck_cluster_label_distance CHECK (cluster_label >= 0 AND distance_to_centroid >= 0), 
	CONSTRAINT ck_cluster_samples CHECK (sample_count > 0 AND expected_sample_count >= sample_count), 
	CONSTRAINT ck_cluster_coverage CHECK (coverage >= 0 AND coverage <= 1)
);
