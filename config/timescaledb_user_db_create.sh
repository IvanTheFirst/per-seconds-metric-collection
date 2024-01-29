#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER fluentbit WITH PASSWORD 'fluentbit';
	GRANT USAGE, CREATE ON SCHEMA public TO fluentbit;
	GRANT SELECT ON ALL TABLES IN SCHEMA public TO fluentbit;
	CREATE DATABASE metrics;
	GRANT ALL PRIVILEGES ON DATABASE metrics TO fluentbit;
	ALTER DATABASE metrics OWNER TO fluentbit;
	CREATE TABLE metrics(
  		time timestamptz NOT NULL,
  		tag text NOT NULL,
  		data jsonb NOT NULL);
	SELECT create_hypertable(
  		'metrics', 'time',
  		chunk_time_interval => INTERVAL '1 day'
	);
EOSQL