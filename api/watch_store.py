"""Transactional browser-local story watchlists."""
import os
from uuid import UUID


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


def create(owner_id, story_id, story_title, story_url, created_at):
    sql = '''INSERT INTO watched_stories (owner_id, story_id, story_title, story_url, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (owner_id, story_id) DO UPDATE SET story_title = EXCLUDED.story_title,
            story_url = EXCLUDED.story_url
        RETURNING *, (xmax = 0) AS created'''
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, (owner_id, story_id, story_title, story_url, created_at))
            return _serialize(cursor.fetchone())
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def list_for_owner(owner_id):
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT * FROM watched_stories WHERE owner_id = %s ORDER BY created_at DESC', (owner_id,))
            return [_serialize(row) for row in cursor.fetchall()]
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error


def remove(owner_id, story_id):
    try:
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute('DELETE FROM watched_stories WHERE owner_id = %s AND story_id = %s RETURNING story_id',
                           (owner_id, story_id))
            return cursor.fetchone() is not None
    except StoreUnavailable:
        raise
    except Exception as error:
        raise StoreUnavailable from error
