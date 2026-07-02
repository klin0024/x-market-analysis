-- Posts: raw X post data
CREATE TABLE IF NOT EXISTS posts (
    id          SERIAL PRIMARY KEY,
    x_post_id   VARCHAR(32) UNIQUE NOT NULL,
    author_id   VARCHAR(32) NOT NULL,
    author_name VARCHAR(128),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (author_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at DESC);

-- Analyses: AI analysis results
CREATE TABLE IF NOT EXISTS analyses (
    id            SERIAL PRIMARY KEY,
    analysis_id   UUID UNIQUE NOT NULL,
    post_id       INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    sentiment     VARCHAR(16) NOT NULL CHECK (sentiment IN ('bullish','bearish','neutral','uncertain')),
    impact_score  NUMERIC(5,2) NOT NULL CHECK (impact_score >= 0 AND impact_score <= 100),
    assets        JSONB,
    summary_zh    TEXT,
    analyzed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analyses_impact_score ON analyses (impact_score DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_analyzed_at ON analyses (analyzed_at DESC);

-- Notifications: LINE push history
CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    notif_id    UUID UNIQUE NOT NULL,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE CASCADE,
    group_id    VARCHAR(64) NOT NULL,
    sent_at     TIMESTAMPTZ,
    status      VARCHAR(16) NOT NULL CHECK (status IN ('sent','failed','skipped','pending'))
);

CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications (sent_at DESC);
