SET 'execution.checkpointing.interval' = '30 s';
SET 'execution.checkpointing.mode' = 'EXACTLY_ONCE';
SET 'execution.checkpointing.externalized-checkpoint-retention' = 'RETAIN_ON_CANCELLATION';
SET 'pipeline.name' = 'pulse-story-windows-v2';
SET 'parallelism.default' = '1';
SET 'table.local-time-zone' = 'UTC';

CREATE TABLE observations (
    schema_version INT,
    event_id STRING,
    source STRING,
    story_id BIGINT,
    title STRING,
    url STRING,
    created_at_epoch BIGINT,
    observed_at TIMESTAMP(3),
    score BIGINT,
    comments BIGINT,
    WATERMARK FOR observed_at AS observed_at - INTERVAL '2' MINUTE
) WITH (
    'connector' = 'kafka',
    'topic' = 'hn.observations.v1',
    'properties.bootstrap.servers' = 'kafka:29092',
    'properties.group.id' = 'pulse-flink-v2',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);

CREATE TABLE story_windows (
    story_id BIGINT,
    window_start TIMESTAMP(3),
    window_end TIMESTAMP(3),
    title STRING,
    score_max BIGINT,
    comments_max BIGINT,
    observation_count BIGINT
) WITH (
    'connector' = 'kafka',
    'topic' = 'hn.story-windows.v2',
    'properties.bootstrap.servers' = 'kafka:29092',
    'sink.delivery-guarantee' = 'at-least-once',
    'format' = 'json'
);

INSERT INTO story_windows
SELECT story_id, window_start, window_end, MAX(title),
       MAX(score), MAX(comments), COUNT(DISTINCT event_id)
FROM TABLE(TUMBLE(TABLE observations, DESCRIPTOR(observed_at), INTERVAL '1' MINUTE))
WHERE schema_version = 1
GROUP BY story_id, window_start, window_end;
