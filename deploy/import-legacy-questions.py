"""Import legacy S3 questions and link them to their PostgreSQL answers.

The legacy JSON entry ID is unrelated to the current integer answer ID. Answers
are therefore matched by user, topic, and the original creation timestamp. The
script is a dry run unless --apply is supplied.
"""

import argparse
import json
import os
from datetime import datetime

import boto3
import psycopg
from psycopg.rows import dict_row


ENTRY_PREFIX = "learning/entries/"
LEGACY_SUBTOPIC_SLUG = "legacy_import"
LEGACY_SUBTOPIC_NAME = "Legacy import"
DIFFICULTIES = {"low": 1, "medium": 3, "high": 5}


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_legacy_entries(s3, bucket: str) -> list[dict]:
    entries = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=ENTRY_PREFIX):
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith(".json"):
                continue
            payload = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
            required = {"entry_id", "technology", "question", "created_at"}
            missing = required - payload.keys()
            if missing:
                raise ValueError(f"{key} is missing: {', '.join(sorted(missing))}")
            entries.append({
                "key": key,
                "entry_id": payload["entry_id"],
                "technology": payload["technology"].lower(),
                "question": payload["question"].strip(),
                "difficulty": DIFFICULTIES.get(payload.get("difficulty") or "medium", 3),
                "created_at": parse_timestamp(payload["created_at"]),
            })
    return entries


def find_matches(conn, entries: list[dict], username: str) -> list[dict]:
    user = conn.execute(
        "SELECT id FROM users WHERE username = %s", (username,)
    ).fetchone()
    if user is None:
        raise ValueError(f"User {username!r} does not exist")

    matches = []
    for entry in entries:
        topic = conn.execute(
            "SELECT id, slug FROM topics WHERE slug = %s", (entry["technology"],)
        ).fetchone()
        if topic is None:
            raise ValueError(f"Topic {entry['technology']!r} does not exist")
        answers = conn.execute(
            """SELECT id, subtopic_id, question_id FROM answers
               WHERE user_id = %s AND topic_id = %s AND created_at = %s""",
            (user["id"], topic["id"], entry["created_at"]),
        ).fetchall()
        if len(answers) != 1:
            raise ValueError(
                f"{entry['key']} matched {len(answers)} answers; expected exactly one"
            )
        matches.append(entry | {
            "topic_id": topic["id"],
            "answer_id": answers[0]["id"],
            "current_subtopic_id": answers[0]["subtopic_id"],
            "current_question_id": answers[0]["question_id"],
        })
    return matches


def import_matches(conn, matches: list[dict]) -> None:
    subtopic_ids = {}
    for match in matches:
        topic_id = match["topic_id"]
        if topic_id not in subtopic_ids:
            row = conn.execute(
                """INSERT INTO subtopics (topic_id, slug, name, is_active)
                   VALUES (%s, %s, %s, false)
                   ON CONFLICT (topic_id, slug) DO UPDATE SET name = EXCLUDED.name
                   RETURNING id""",
                (topic_id, LEGACY_SUBTOPIC_SLUG, LEGACY_SUBTOPIC_NAME),
            ).fetchone()
            subtopic_ids[topic_id] = row["id"]

        subtopic_id = subtopic_ids[topic_id]
        row = conn.execute(
            """INSERT INTO questions
               (topic_id, subtopic_id, text, difficulty, is_active)
               VALUES (%s, %s, %s, %s, false)
               ON CONFLICT DO NOTHING RETURNING id""",
            (topic_id, subtopic_id, match["question"], match["difficulty"]),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """SELECT id FROM questions
                   WHERE subtopic_id = %s AND lower(text) = lower(%s)""",
                (subtopic_id, match["question"]),
            ).fetchone()
        question_id = row["id"]

        current_question_id = match["current_question_id"]
        if current_question_id not in (None, question_id):
            raise ValueError(
                f"Answer {match['answer_id']} is already linked to question "
                f"{current_question_id}, not {question_id}"
            )
        conn.execute(
            """UPDATE answers SET subtopic_id = %s, question_id = %s
               WHERE id = %s""",
            (subtopic_id, question_id, match["answer_id"]),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="write the verified links; without this flag the script is read-only",
    )
    args = parser.parse_args()

    dsn = os.environ["LEARNIKAL_DATABASE_URL"]
    bucket = os.environ["LEARNIKAL_S3_BUCKET"]
    username = os.getenv("LEARNIKAL_USERNAME", "kalin")
    entries = read_legacy_entries(boto3.client("s3"), bucket)

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        matches = find_matches(conn, entries, username)
        for match in matches:
            print(
                f"{match['key']} -> answer {match['answer_id']} "
                f"({match['technology']}): {match['question']}"
            )
        if args.apply:
            import_matches(conn, matches)
        else:
            conn.rollback()

    action = "Imported" if args.apply else "Verified (dry run)"
    print(f"{action}: {len(matches)} legacy question(s)")


if __name__ == "__main__":
    main()
