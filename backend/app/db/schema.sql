CREATE TABLE IF NOT EXISTS query_cache (
    query TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    ttl_seconds INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS video_metadata (
    video_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_name TEXT,
    channel_url TEXT,
    duration_text TEXT,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    watch_url TEXT NOT NULL,
    last_seen INTEGER NOT NULL
);
