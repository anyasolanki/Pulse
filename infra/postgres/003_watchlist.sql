CREATE TABLE IF NOT EXISTS watched_stories (
    owner_id UUID NOT NULL,
    story_id BIGINT NOT NULL CHECK (story_id > 0),
    story_title TEXT NOT NULL,
    story_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (owner_id, story_id)
);

CREATE INDEX IF NOT EXISTS watched_stories_owner_created_idx
ON watched_stories (owner_id, created_at DESC);
