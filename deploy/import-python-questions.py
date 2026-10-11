"""Import the reviewed Python question bank without replacing existing questions."""

import argparse
import csv
import os
from pathlib import Path

import psycopg


CSV_PATH = Path(__file__).resolve().parents[1] / "docs" / "python-questions.csv"
CATALOG_PATH = Path(__file__).resolve().parents[1] / "docs" / "subtopics-catalog.csv"
DSN = os.getenv("LEARNIKAL_DATABASE_URL", "dbname=learnikal user=postgres")


def load_bank():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["subtopic_slug", "difficulty", "text"]:
            raise ValueError("Unexpected Python question bank columns")
        rows = list(reader)
    with CATALOG_PATH.open(encoding="utf-8-sig", newline="") as source:
        expected = {row["subtopic_slug"] for row in csv.DictReader(source)
                    if row["topic_slug"] == "python"}
    slugs = [row["subtopic_slug"] for row in rows]
    if len(rows) != len(expected) or set(slugs) != expected:
        raise ValueError("Bank must contain one question for every Python subtopic")
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate Python subtopic in bank")
    for row in rows:
        if row["difficulty"] != "2" or not row["text"].strip():
            raise ValueError(f"Invalid question for {row['subtopic_slug']}")
    return rows


def import_bank(conn, rows, *, apply=False):
    conn.execute("SET ROLE learnikal")
    topic = conn.execute("SELECT id FROM topics WHERE slug = 'python' AND is_active = true").fetchone()
    if topic is None:
        raise ValueError("Active Python topic is missing")
    topic_id = topic[0]
    subtopics = dict(conn.execute(
        "SELECT slug, id FROM subtopics WHERE topic_id = %s AND is_active = true",
        (topic_id,),
    ).fetchall())
    missing = {row["subtopic_slug"] for row in rows} - subtopics.keys()
    if missing:
        raise ValueError(f"Active Python subtopics missing: {', '.join(sorted(missing))}")

    inserted = 0
    for row in rows:
        subtopic_id = subtopics[row["subtopic_slug"]]
        existing = conn.execute(
            """SELECT is_active FROM questions
               WHERE subtopic_id = %s AND lower(text) = lower(%s)""",
            (subtopic_id, row["text"]),
        ).fetchone()
        if existing is not None:
            if not existing[0]:
                raise ValueError(f"Question is inactive: {row['subtopic_slug']}")
            continue
        inserted += 1
        if apply:
            conn.execute(
                """INSERT INTO questions (topic_id, subtopic_id, text, difficulty, is_active)
                   VALUES (%s, %s, %s, %s, true)""",
                (topic_id, subtopic_id, row["text"], int(row["difficulty"])),
            )
    if not apply:
        conn.rollback()
    return inserted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert missing questions")
    parser.add_argument("--validate", action="store_true", help="Validate CSV without a database")
    args = parser.parse_args()
    rows = load_bank()
    if args.validate:
        print(f"Validated {len(rows)} Python questions")
        return
    with psycopg.connect(DSN) as conn:
        count = import_bank(conn, rows, apply=args.apply)
    action = "Inserted" if args.apply else "Would insert"
    print(f"{action} {count} of {len(rows)} Python questions")


if __name__ == "__main__":
    main()
