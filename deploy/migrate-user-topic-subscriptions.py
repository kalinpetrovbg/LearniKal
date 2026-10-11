"""Create topic subscriptions and preserve the existing learning user's catalog."""

import os

import psycopg


DSN = os.getenv("LEARNIKAL_DATABASE_URL", "dbname=learnikal user=postgres")
DEFAULT_USERNAME = os.getenv("LEARNIKAL_USERNAME", "kalin").lower()


def migrate(conn, default_username=DEFAULT_USERNAME):
    conn.execute("SET ROLE learnikal")
    existed = conn.execute(
        "SELECT to_regclass('public.user_topic_subscriptions')"
    ).fetchone()[0] is not None
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_topic_subscriptions (
               user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               topic_id bigint NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
               created_at timestamptz NOT NULL DEFAULT now(),
               PRIMARY KEY (user_id, topic_id)
           )"""
    )
    # Seed only when the table is first created. Later deploys must respect unsubscribes.
    if not existed:
        conn.execute(
            """INSERT INTO user_topic_subscriptions (user_id, topic_id)
               SELECT u.id, t.id FROM users u CROSS JOIN topics t
               WHERE lower(u.username) = %s AND t.is_active = true
               ON CONFLICT DO NOTHING""",
            (default_username,),
        )
    return conn.execute("SELECT COUNT(*) FROM user_topic_subscriptions").fetchone()[0]


def main():
    with psycopg.connect(DSN) as conn:
        count = migrate(conn)
    print(f"Verified user topic subscriptions: {count}")


if __name__ == "__main__":
    main()
