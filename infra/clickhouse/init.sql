CREATE DATABASE IF NOT EXISTS pulse;

CREATE TABLE IF NOT EXISTS pulse.story_windows (
    story_id UInt64,
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    title String,
    score_max UInt64,
    comments_max UInt64,
    observation_count UInt64
) ENGINE = ReplacingMergeTree
ORDER BY (story_id, window_start, window_end);

CREATE TABLE IF NOT EXISTS pulse.windows_queue (
    story_id UInt64,
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    title String,
    score_max UInt64,
    comments_max UInt64,
    observation_count UInt64
) ENGINE = Kafka
SETTINGS kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'hn.story-windows.v1',
    kafka_group_name = 'pulse-clickhouse-v1',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS pulse.consume_windows
TO pulse.story_windows AS SELECT * FROM pulse.windows_queue;
