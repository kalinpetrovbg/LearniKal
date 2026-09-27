"""Remove replaced learning tables after the new API passes its health check."""

import psycopg


def main() -> None:
    with psycopg.connect("dbname=learnikal user=postgres") as conn:
        conn.execute("SET ROLE learnikal")
        documents_exist = conn.execute(
            "SELECT to_regclass('public.learning_documents')"
        ).fetchone()[0] is not None
        if documents_exist:
            missing = conn.execute(
                '''SELECT d.name FROM learning_documents d
                   WHERE NOT EXISTS (
                       SELECT 1 FROM instructions i
                       WHERE i."type" = d.name AND i.text = d.content AND i.is_active = true
                   ) ORDER BY d.name'''
            ).fetchall()
            if missing:
                raise RuntimeError(
                    "Learning documents were not preserved as typed instructions: "
                    + ", ".join(row[0] for row in missing)
                )
            conn.execute("DROP TABLE public.learning_documents")
        conn.execute("DROP TABLE IF EXISTS public.history_sections")
        conn.execute("DROP TABLE IF EXISTS public.learning_state")
        remaining = conn.execute(
            """SELECT to_regclass('public.history_sections'),
                      to_regclass('public.learning_state'),
                      to_regclass('public.learning_documents')"""
        ).fetchone()
        if remaining != (None, None, None):
            raise RuntimeError(f"Obsolete tables remain: {remaining}")
    print("Verified replaced learning tables are absent")


if __name__ == "__main__":
    main()
