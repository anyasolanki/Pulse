"""Live integration check: event-time attribution and duplicate Kafka replay.

Re-publishes one existing immutable observation twice; no invented data is used.
"""
import json
import time
from pipeline import docker


def query(sql):
    output = docker('exec', '-T', 'clickhouse', 'clickhouse-client', '--user', 'pulse',
                    '--password', 'pulse-local', '--query', sql + ' FORMAT JSONEachRow')
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def main():
    # An old, closed event-time window gives stable expected results while ingestion continues.
    windows = query('SELECT * FROM pulse.story_windows_v2 FINAL ORDER BY window_end LIMIT 1')
    if not windows:
        raise SystemExit('No event-time windows yet. Start the pipeline and wait for watermarks.')
    window = windows[0]
    story = int(window['story_id'])
    start, end = window['window_start'], window['window_end']
    rows = query(f"SELECT * FROM pulse.observations FINAL WHERE story_id = {story} AND observed_at >= '{start}' AND observed_at < '{end}' ORDER BY observed_at")
    assert rows, 'Missing raw evidence'
    assert int(window['score_max']) == max(int(row['score']) for row in rows), 'Score maximum differs from raw history'
    assert int(window['comments_max']) == max(int(row['comments']) for row in rows), 'Comment maximum differs from raw history'
    assert int(window['observation_count']) == len(rows), 'Distinct observation count differs'
    print('PASS: historical window boundaries and aggregates match raw collection times.', flush=True)

    event = rows[0]
    for key in ('schema_version', 'story_id', 'created_at_epoch', 'score', 'comments'):
        event[key] = int(event[key])
    # JSON encoding is used for transport only; SQL literals are escaped independently.
    event_id = event['event_id'].replace('\\', '\\\\').replace("'", "\\'")
    where = f"WHERE story_id = {story} AND event_id = '{event_id}'"
    producer = """import json,sys
from kafka import KafkaProducer
event=json.load(sys.stdin)
p=KafkaProducer(bootstrap_servers='kafka:29092',acks='all',value_serializer=lambda x:json.dumps(x).encode())
for _ in range(2):
    metadata=p.send('hn.observations.v1',key=str(event['story_id']).encode(),value=event).get(timeout=30)
p.close()
print(metadata.offset + 1)
"""
    # Kafka consumer commits its offset after writing the batch. Wait for that commit,
    # rather than relying on physical row counts which background merges can change.
    def offset(output, group):
        for line in output.splitlines():
            fields = line.split()
            if len(fields) > 3 and fields[0] == group and fields[1] == 'hn.observations.v1':
                return int(fields[3])
        return -1
    target = int(docker('exec', '-T', 'ingestion', 'python', '-c', producer, input=json.dumps(event)).strip())
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        consumed = []
        for group in ('pulse-raw-clickhouse-v1', 'pulse-flink-v2'):
            current = docker('exec', '-T', 'kafka', '/opt/kafka/bin/kafka-consumer-groups.sh',
                             '--bootstrap-server', 'kafka:29092', '--group', group, '--describe')
            consumed.append(offset(current, group) >= target)
        if all(consumed):
            break
        time.sleep(2)
    else:
        raise AssertionError('Replay offset was not committed by both consumers within 90 seconds')
    count = query('SELECT count() AS n FROM pulse.observations FINAL ' + where)[0]['n']
    assert int(count) == 1, 'Replay inflated the raw history'
    after = query(f"SELECT * FROM pulse.story_windows_v2 FINAL WHERE story_id = {story} AND window_start = '{start}'")
    assert after == [window], 'Replay changed the closed event-time window'
    print('PASS: duplicate Kafka replay leaves one logical raw event and unchanged closed window.', flush=True)


if __name__ == '__main__':
    main()
