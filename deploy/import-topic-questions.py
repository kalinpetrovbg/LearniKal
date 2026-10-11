"""Import the expanded question bank without replacing existing questions."""

import argparse
import csv
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "docs" / "topic-questions.csv"
CATALOG_PATH = ROOT / "docs" / "subtopics-catalog.csv"
PYTHON_PATHS = [ROOT / "docs" / "python-questions.csv",
                ROOT / "docs" / "python-questions-extra.csv"]
DSN = os.getenv("LEARNIKAL_DATABASE_URL", "dbname=learnikal user=postgres")


def load_bank():
    with CATALOG_PATH.open(encoding="utf-8-sig", newline="") as source:
        catalog = {(row["topic_slug"], row["subtopic_slug"])
                   for row in csv.DictReader(source)}
    existing_texts = set()
    for path in PYTHON_PATHS:
        with path.open(encoding="utf-8-sig", newline="") as source:
            existing_texts.update(
                ("python", row["subtopic_slug"], row["text"].strip().casefold())
                for row in csv.DictReader(source)
            )
    with BANK_PATH.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["topic_slug", "subtopic_slug", "difficulty", "text"]:
            raise ValueError("Unexpected topic question bank columns")
        rows = list(reader)

    actual = Counter()
    texts = set(existing_texts)
    included = set()
    for row in rows:
        try:
            difficulty = int(row["difficulty"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid difficulty: {row!r}") from exc
        key = (row["topic_slug"], row["subtopic_slug"], difficulty)
        if not row["text"].strip() or (key[0], key[1]) not in catalog or difficulty not in range(1, 6):
            raise ValueError(f"Invalid question: {row!r}")
        included.add((key[0], key[1]))
        text_key = (row["topic_slug"], row["subtopic_slug"], row["text"].strip().casefold())
        if text_key in texts:
            raise ValueError(f"Duplicate question text: {key}")
        texts.add(text_key)
        actual[key] += 1
    expected = {(topic, subtopic, difficulty): (4 if topic == "python" else 5)
                for topic, subtopic in included for difficulty in range(1, 6)}
    mismatches = {key: (actual[key], count) for key, count in expected.items()
                  if actual[key] != count}
    if mismatches:
        raise ValueError(f"Question counts differ for {len(mismatches)} catalog/difficulty pairs")
    return rows, included


def import_bank(conn, rows, included, *, apply=False):
    conn.execute("SET ROLE learnikal")
    available = {(topic, subtopic): (topic_id, subtopic_id)
                 for topic, subtopic, topic_id, subtopic_id in conn.execute(
                     """SELECT t.slug, s.slug, t.id, s.id
                        FROM topics t JOIN subtopics s ON s.topic_id = t.id
                        WHERE t.is_active = true AND s.is_active = true"""
                 ).fetchall()}
    missing = included - available.keys()
    if missing:
        raise ValueError(f"Active catalog entries missing: {len(missing)}")
    inserted = 0
    for row in rows:
        topic_id, subtopic_id = available[(row["topic_slug"], row["subtopic_slug"])]
        existing = conn.execute(
            """SELECT is_active, difficulty FROM questions
               WHERE subtopic_id = %s AND lower(text) = lower(%s)""",
            (subtopic_id, row["text"]),
        ).fetchone()
        if existing is not None:
            if not existing[0] or existing[1] != int(row["difficulty"]):
                raise ValueError(f"Conflicting question: {row['topic_slug']}/{row['subtopic_slug']}")
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
    rows, included = load_bank()
    if args.validate:
        print(f"Validated {len(rows)} expanded questions across {len(included)} subtopics")
        return
    import psycopg

    with psycopg.connect(DSN) as conn:
        count = import_bank(conn, rows, included, apply=args.apply)
    print(f"{'Inserted' if args.apply else 'Would insert'} {count} of {len(rows)} questions")


if __name__ == "__main__":
    main()
