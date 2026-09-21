CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS topics (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z][a-z0-9_-]{0,39}$')
);

CREATE TABLE IF NOT EXISTS learning_documents (
    name text PRIMARY KEY CHECK (name IN ('plan', 'knowledge', 'handoff', 'history', 'patterns')),
    content text NOT NULL,
    sha256 text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_policy (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    instructions text NOT NULL
);

CREATE TABLE IF NOT EXISTS history_sections (
    position integer PRIMARY KEY,
    heading text NOT NULL,
    body text NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_entries (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    topic_id bigint NOT NULL REFERENCES topics(id),
    question text NOT NULL CHECK (btrim(question) <> ''),
    answer text NOT NULL CHECK (btrim(answer) <> ''),
    evaluation jsonb,
    next_question text,
    difficulty text CHECK (difficulty IN ('low', 'medium', 'high')),
    score smallint CHECK (score BETWEEN 0 AND 5),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS learning_entries_user_topic_recent
    ON learning_entries (user_id, topic_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS learning_state (
    user_id uuid PRIMARY KEY REFERENCES users(id),
    next_topic_id bigint REFERENCES topics(id),
    next_question text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
