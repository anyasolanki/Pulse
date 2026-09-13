"""Small transactional store for local Pulse calls; analytical evidence stays in ClickHouse."""
import os
from uuid import UUID, uuid4


class StoreUnavailable(Exception):
    pass


def _connect():
    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(os.getenv('POSTGRES_URL', 'postgresql://pulse:pulse-local@localhost:5432/pulse'),
                               row_factory=dict_row)
    except Exception as error:
        raise StoreUnavailable from error


def _serialize(row):
    return {key: (str(value) if isinstance(value, UUID) else value) for key, value in row.items()}


def create(owner_id, story_id, story_title, call, confidence, created_at, expires_at):
    sql = '''INSERT INTO predictions
        (id, owner_id, story_id, story_title, call, confidence, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (owner_id, story_id) DO NOTHING
        RETURNING *'''
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, (uuid4(), owner_id, story_id, story_title, call, confidence, created_at, expires_at))
            row = cursor.fetchone()
        return _serialize(row) if row else None
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def list_for_owner(owner_id):
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT * FROM predictions WHERE owner_id = %s ORDER BY created_at DESC', (owner_id,))
            return [_serialize(row) for row in cursor.fetchall()]
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def due_for_owner(owner_id, now):
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute('''SELECT * FROM predictions
                WHERE owner_id = %s AND status = 'pending' AND expires_at <= %s
                ORDER BY expires_at''', (owner_id, now))
            return [_serialize(row) for row in cursor.fetchall()]
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def profile_for_owner(owner_id):
    sql = '''SELECT count(*)::int AS total,
        count(*) FILTER (WHERE status = 'pending')::int AS pending,
        count(*) FILTER (WHERE status = 'resolved')::int AS resolved,
        count(*) FILTER (WHERE status = 'unverifiable')::int AS unverifiable,
        count(*) FILTER (WHERE status = 'resolved' AND correct IS NOT NULL)::int AS scored,
        count(*) FILTER (WHERE status = 'resolved' AND correct = TRUE)::int AS correct,
        (avg(extract(epoch FROM first_qualified_at - created_at) / 60.0)
            FILTER (WHERE status = 'resolved' AND correct = TRUE AND call = 'yes'
                    AND first_qualified_at IS NOT NULL))::float8 AS average_early_minutes
        FROM predictions WHERE owner_id = %s'''
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, (owner_id,))
            record = dict(cursor.fetchone())
        record['accuracy'] = (record['correct'] / record['scored'] * 100) if record['scored'] else None
        return record
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def resolve(prediction_id, owner_id, resolution, resolved_at):
    sql = '''UPDATE predictions SET status = %s, outcome = %s, correct = %s,
            outcome_reason = %s, first_qualified_at = %s, resolution_checks = %s,
            covered_checks = %s, resolved_at = %s
        WHERE id = %s AND owner_id = %s AND status = 'pending'
        RETURNING *'''
    outcome = resolution.get('outcome')
    correct = outcome is not None and ((outcome and resolution['call'] == 'yes') or (not outcome and resolution['call'] == 'no'))
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, (resolution['status'], outcome, correct if outcome is not None else None,
                resolution['reason'], resolution.get('first_qualified_at'), resolution['checks'],
                resolution['covered_checks'], resolved_at, prediction_id, owner_id))
            row = cursor.fetchone()
        return _serialize(row) if row else None
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error
