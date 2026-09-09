"""Explicit local Flink lifecycle with durable savepoint restore."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / 'infra/flink/pipeline.sql'
STATE = ROOT / '.pulse/savepoint.json'


def docker(*args, input=None):
    binary = shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
    env = dict(os.environ)
    env['PATH'] = str(Path(binary).parent) + os.pathsep + env.get('PATH', '')
    result = subprocess.run([binary, 'compose', *args], cwd=ROOT, env=env,
                            input=input, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout


def jobs():
    with urlopen('http://localhost:8081/jobs/overview', timeout=10) as response:
        return json.load(response)['jobs']


def active():
    return [job for job in jobs() if job['state'] not in ('FINISHED', 'FAILED', 'CANCELED')]


def digest():
    return hashlib.sha256(SQL.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status', 'stop', 'restore'])
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(jobs(), indent=2))
        return
    running = active()
    if args.action == 'stop':
        if len(running) != 1 or running[0]['name'] != 'pulse-story-windows-v2':
            raise SystemExit('Expected exactly one running Pulse v2 job; inspect status first.')
        output = docker('exec', '-T', 'jobmanager', '/opt/flink/bin/flink', 'stop',
                        '--savepointPath', 'file:///opt/flink/state/savepoints', running[0]['jid'])
        print(output)
        match = re.search(r'(file:/\S*savepoint-\S+)', output)
        if not match:
            raise SystemExit('Savepoint path not found; inspect output before restarting.')
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps({'path': match.group(1).rstrip('.'), 'sql_sha256': digest()}, indent=2))
        print(f'Saved restore information to {STATE}')
        return
    if running:
        raise SystemExit('A job is already active; refusing duplicate submission.')
    sql = SQL.read_text()
    if args.action == 'restore':
        state = json.loads(STATE.read_text())
        if state['sql_sha256'] != digest():
            raise SystemExit('SQL changed since savepoint. Review state compatibility before restoring.')
        path = state['path']
        if not re.fullmatch(r'file:/[\w/.-]+', path):
            raise SystemExit('Invalid savepoint path')
        sql = f"SET 'execution.savepoint.path' = '{path}';\n" + sql
    elif STATE.exists():
        raise SystemExit('A saved state exists. Use restore to preserve offsets and open windows.')
    output = docker('exec', '-T', 'jobmanager', '/opt/flink/bin/sql-client.sh', '-f', '/dev/stdin', input=sql)
    print(output)
    # Flink SQL client can exit 0 even when a statement failed.
    if '[ERROR]' in output or not re.search(r'Job ID: [a-f0-9]{32}', output):
        raise SystemExit('SQL submission failed; see output above.')


if __name__ == '__main__':
    main()
