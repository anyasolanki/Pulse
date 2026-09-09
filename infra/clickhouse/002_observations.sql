-- Additive migration: keep phase-1 processing-time tables for comparison.
CREATE DATABASE IF NOT EXISTS pulse;
CREATE TABLE IF NOT EXISTS pulse.observations (
    schema_version UInt32,
    event_id String,
    source LowCardinality(String),
    story_id UInt64,
    title String,
    url String,
    created_at_epoch UInt64,
    observed_at DateTime64(3, 'UTC'),
    score Int64,
    comments Int64
) ENGINE = ReplacingMergeTree
ORDER BY (story_id, observed_at, event_id);

CREATE TABLE IF NOT EXISTS pulse.observations_queue (
    schema_version UInt32,
    event_id String,
    source String,
    story_id UInt64,
    title String,
    url String,
    created_at_epoch UInt64,
    observed_at DateTime64(3, 'UTC'),
    score Int64,
    comments Int64
) ENGINE = Kafka
SETTINGS kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'hn.observations.v1',
    kafka_group_name = 'pulse-raw-clickhouse-v1',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS pulse.consume_observations
TO pulse.observations AS SELECT * FROM pulse.observations_queue;

CREATE TABLE IF NOT EXISTS pulse.story_windows_v2 (
    story_id UInt64,
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    title String,
    score_max UInt64,
    comments_max UInt64,
    observation_count UInt64
) ENGINE = ReplacingMergeTree
ORDER BY (story_id, window_start, window_end);

CREATE TABLE IF NOT EXISTS pulse.windows_queue_v2 (
    story_id UInt64,
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    title String,
    score_max UInt64,
    comments_max UInt64,
    observation_count UInt64
) ENGINE = Kafka
SETTINGS kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'hn.story-windows.v2',
    kafka_group_name = 'pulse-clickhouse-v2',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS pulse.consume_windows_v2
TO pulse.story_windows_v2 AS SELECT * FROM pulse.windows_queue_v2;
