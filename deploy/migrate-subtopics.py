"""Create the subtopics catalog table."""

import psycopg


def migrate(conn):
    conn.execute("SET ROLE learnikal")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS subtopics (
               id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
               topic_id bigint NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
               slug text NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_-]{0,39}$'),
               name text NOT NULL CHECK (btrim(name) <> ''),
               is_active boolean NOT NULL DEFAULT true,
               created_at timestamptz NOT NULL DEFAULT now(),
               updated_at timestamptz NOT NULL DEFAULT now(),
               UNIQUE (topic_id, slug)
           )"""
    )
    conn.execute("ALTER TABLE subtopics DROP CONSTRAINT IF EXISTS subtopics_topic_id_fkey")
    conn.execute(
        """ALTER TABLE subtopics
           ADD CONSTRAINT subtopics_topic_id_fkey
           FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE"""
    )
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS subtopics_topic_name_lower_key
           ON subtopics (topic_id, lower(name))"""
    )
    conn.execute(
        """CREATE OR REPLACE FUNCTION set_updated_at()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               NEW.updated_at = now();
               RETURN NEW;
           END;
           $$"""
    )
    conn.execute("DROP TRIGGER IF EXISTS subtopics_set_updated_at ON subtopics")
    conn.execute(
        """CREATE TRIGGER subtopics_set_updated_at BEFORE UPDATE ON subtopics
           FOR EACH ROW EXECUTE FUNCTION set_updated_at()"""
    )
    return conn.execute("SELECT COUNT(*) FROM subtopics").fetchone()[0]


def main():
    with psycopg.connect("dbname=learnikal user=postgres") as conn:
        count = migrate(conn)
    print(f"Verified subtopics table: {count} subtopic(s)")


if __name__ == "__main__":
    main()
