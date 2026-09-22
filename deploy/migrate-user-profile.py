"""Apply the user-profile columns to an existing LearniKal database."""

import argparse
import getpass

import psycopg
from argon2 import PasswordHasher, Type


PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)


def migrate(conn, username, first_name, last_name, email, password):
    if not all(value and value.strip() for value in (username, first_name, last_name, email, password)):
        raise ValueError("Profile fields and password must not be empty")

    conn.execute("SET ROLE learnikal")
    user = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
    if user is None:
        raise ValueError(f"User {username!r} does not exist")

    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name text")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name text")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email text")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()")

    encoded = PASSWORD_HASHER.hash(password)
    conn.execute(
        """UPDATE users SET first_name = %s, last_name = %s, email = %s,
                  password_hash = %s WHERE id = %s""",
        (first_name, last_name, email, encoded, user[0]),
    )
    missing = conn.execute(
        """SELECT COUNT(*) FROM users WHERE first_name IS NULL OR last_name IS NULL
           OR email IS NULL OR password_hash IS NULL"""
    ).fetchone()[0]
    if missing:
        raise ValueError(f"{missing} other user(s) need profile values before adding NOT NULL constraints")

    for column in ("first_name", "last_name", "email", "password_hash"):
        conn.execute(f"ALTER TABLE users ALTER COLUMN {column} SET NOT NULL")

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_key ON users (lower(username))")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (lower(email))")
    conn.execute(
        """CREATE OR REPLACE FUNCTION set_updated_at()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               NEW.updated_at = now();
               RETURN NEW;
           END;
           $$"""
    )
    conn.execute("DROP TRIGGER IF EXISTS users_set_updated_at ON users")
    conn.execute(
        """CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
           FOR EACH ROW EXECUTE FUNCTION set_updated_at()"""
    )
    stored = conn.execute("SELECT password_hash FROM users WHERE id = %s", (user[0],)).fetchone()[0]
    if not PASSWORD_HASHER.verify(stored, password):
        raise ValueError("Password hash verification failed")
    return user[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password for this user: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; database was not changed")
    with psycopg.connect("dbname=learnikal user=postgres") as conn:
        user_id = migrate(conn, args.username, args.first_name, args.last_name, args.email, password)
    print(f"Updated user {args.username} (id={user_id})")


if __name__ == "__main__":
    main()
