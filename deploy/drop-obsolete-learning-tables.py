"""Drop derived/unused learning tables after the API no longer reads them."""

import psycopg


def main() -> None:
    with psycopg.connect("dbname=learnikal user=postgres") as conn:
        conn.execute("SET ROLE learnikal")
        conn.execute("DROP TABLE IF EXISTS public.history_sections")
        conn.execute("DROP TABLE IF EXISTS public.learning_state")
        remaining = conn.execute(
            """SELECT to_regclass('public.history_sections'),
                      to_regclass('public.learning_state')"""
        ).fetchone()
        if remaining != (None, None):
            raise RuntimeError(f"Obsolete tables remain: {remaining}")
    print("Verified obsolete learning tables are absent")


if __name__ == "__main__":
    main()
