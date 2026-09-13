CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    story_id BIGINT NOT NULL CHECK (story_id > 0),
    story_title TEXT NOT NULL,
    call TEXT NOT NULL CHECK (call IN ('yes', 'no')),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'resolved', 'unverifiable')),
    outcome BOOLEAN,
    correct BOOLEAN,
    outcome_reason TEXT,
    first_qualified_at TIMESTAMPTZ,
    resolution_checks INTEGER,
    covered_checks INTEGER,
    resolved_at TIMESTAMPTZ,
    UNIQUE (owner_id, story_id)
);

CREATE INDEX IF NOT EXISTS predictions_owner_created_idx ON predictions (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS predictions_pending_expiry_idx ON predictions (owner_id, expires_at)
WHERE status = 'pending';
