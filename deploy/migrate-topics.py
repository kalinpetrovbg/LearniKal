"""Apply the LearniKal topic catalog columns to an existing database."""

import psycopg


TOPIC_NAMES = {
    "ai": "AI",
    "airflow": "Airflow",
    "clickhouse": "ClickHouse",
    "data_engineering": "Data Engineering",
    "design_patterns": "Design Patterns",
    "docker": "Docker",
    "kafka": "Kafka",
    "pandas_polars": "Pandas / Polars",
    "postgresql": "PostgreSQL",
    "python": "Python",
    "redis": "Redis",
    "rest_api": "REST API",
    "testing": "Testing",
}


def migrate(conn):
    conn.execute("SET ROLE learnikal")
    conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS name text")
    conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true")
    conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()")
    conn.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()")

    legacy_ai = conn.execute("SELECT id FROM topics WHERE slug = 'ai_rag'").fetchone()
    current_ai = conn.execute("SELECT id FROM topics WHERE slug = 'ai'").fetchone()
    if legacy_ai and current_ai:
        raise ValueError("Both ai and ai_rag topics exist; refusing an ambiguous migration")
    if legacy_ai:
        conn.execute("UPDATE topics SET slug = 'ai' WHERE id = %s", (legacy_ai[0],))

    for slug, name in TOPIC_NAMES.items():
        conn.execute(
            "UPDATE topics SET name = %s WHERE slug = %s AND name IS DISTINCT FROM %s",
            (name, slug, name),
        )
        if conn.execute("SELECT 1 FROM topics WHERE slug = %s", (slug,)).fetchone() is None:
            raise ValueError(f"Required topic {slug!r} is missing")

    unnamed = [row[0] for row in conn.execute(
        "SELECT slug FROM topics WHERE name IS NULL ORDER BY slug"
    ).fetchall()]
    if unnamed:
        raise ValueError(f"Topics require names: {', '.join(unnamed)}")

    conn.execute("ALTER TABLE topics ALTER COLUMN name SET NOT NULL")
    conn.execute("ALTER TABLE topics DROP CONSTRAINT IF EXISTS topics_name_not_blank")
    conn.execute("ALTER TABLE topics ADD CONSTRAINT topics_name_not_blank CHECK (btrim(name) <> '')")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS topics_name_lower_key ON topics (lower(name))")
    conn.execute(
        """CREATE OR REPLACE FUNCTION set_updated_at()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               NEW.updated_at = now();
               RETURN NEW;
           END;
           $$"""
    )
    conn.execute("DROP TRIGGER IF EXISTS topics_set_updated_at ON topics")
    conn.execute(
        """CREATE TRIGGER topics_set_updated_at BEFORE UPDATE ON topics
           FOR EACH ROW EXECUTE FUNCTION set_updated_at()"""
    )
    return conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]


def main():
    with psycopg.connect("dbname=learnikal user=postgres") as conn:
        count = migrate(conn)
    print(f"Updated {count} topics")


if __name__ == "__main__":
    main()
