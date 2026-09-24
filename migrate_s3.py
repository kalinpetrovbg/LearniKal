"""One-time, repeatable import from the old S3 store into PostgreSQL."""

import hashlib
import json
import os
import re
from pathlib import Path

import boto3
import psycopg

from learnikal.models import Entry
from learnikal.postgres import DOCUMENTS, STUDY_RULES


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


def history_sections(content: str):
    headings = list(re.finditer(r"^### (.+)$", content, re.MULTILINE))
    return [
        (position, match.group(1).strip(),
         content[match.end():headings[position + 1].start() if position + 1 < len(headings) else len(content)].strip())
        for position, match in enumerate(headings)
    ]


def pending_question(content: str):
    match = re.search(r"^## Следващ въпрос\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    lines = [line.strip() for line in match.group(1).strip().splitlines()]
    question = " ".join(line for line in lines if line and not line.startswith("Без код."))
    return question or None


def read_source(s3, bucket):
    documents = {}
    for name, filename in DOCUMENTS.items():
        body = s3.get_object(
            Bucket=bucket, Key=f"learning/documents/{filename}"
        )["Body"].read()
        documents[name] = body.decode("utf-8")

    entries = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="learning/entries/"):
        for item in page.get("Contents", []):
            if not item["Key"].endswith(".json"):
                continue
            body = s3.get_object(Bucket=bucket, Key=item["Key"])["Body"].read()
            raw_entry = json.loads(body)
            legacy_entry_id = raw_entry.pop("entry_id")
            entry = Entry.model_validate({**raw_entry, "entry_id": None})
            expected_key = f"learning/entries/{entry.technology}/{legacy_entry_id}.json"
            if item["Key"] != expected_key:
                raise ValueError(f"S3 entry key does not match content: {item['Key']}")
            entries.append((legacy_entry_id, entry))
    if len({legacy_id for legacy_id, _entry in entries}) != len(entries):
        raise ValueError("Duplicate entry IDs in S3")
    return documents, entries


def migrate(conn, documents, entries, username):
    conn.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    user = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
    if user is None:
        raise ValueError(f"User {username!r} must be created before importing S3 data")
    user_id = user[0]
    conn.execute(
        "INSERT INTO learning_policy (id, instructions) VALUES (true, %s) ON CONFLICT (id) DO NOTHING",
        (STUDY_RULES,),
    )

    entry_topics = {entry.technology for _legacy_id, entry in entries}
    unknown_topics = entry_topics - TOPIC_NAMES.keys()
    if unknown_topics:
        raise ValueError(f"Missing topic metadata for: {', '.join(sorted(unknown_topics))}")
    for slug, name in TOPIC_NAMES.items():
        conn.execute(
            """INSERT INTO topics (slug, name) VALUES (%s, %s)
               ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name""",
            (slug, name),
        )
    topic_ids = dict(conn.execute("SELECT slug, id FROM topics").fetchall())

    for name, content in documents.items():
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = conn.execute(
            "SELECT sha256 FROM learning_documents WHERE name = %s", (name,)
        ).fetchone()
        if existing and existing[0] != digest:
            raise ValueError(f"PostgreSQL document {name} differs from S3; refusing overwrite")
        conn.execute(
            """INSERT INTO learning_documents (name, content, sha256)
               VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING""",
            (name, content, digest),
        )

    for position, heading, body in history_sections(documents["history"]):
        conn.execute(
            """INSERT INTO history_sections (position, heading, body)
               VALUES (%s, %s, %s) ON CONFLICT (position) DO UPDATE SET
               heading = EXCLUDED.heading, body = EXCLUDED.body""",
            (position, heading, body),
        )

    for _legacy_id, entry in entries:
        from psycopg.types.json import Jsonb

        existing = conn.execute(
            """SELECT id FROM learning_entries
               WHERE user_id = %s AND topic_id = %s AND question = %s
                 AND answer = %s AND created_at = %s""",
            (user_id, topic_ids[entry.technology], entry.question, entry.answer, entry.created_at),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """INSERT INTO learning_entries
               (user_id, topic_id, question, answer, evaluation, next_question,
                difficulty, score, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, topic_ids[entry.technology], entry.question, entry.answer,
             Jsonb(entry.evaluation.model_dump()) if entry.evaluation else None,
             entry.next_question, entry.difficulty, entry.score, entry.created_at),
        )

    question = pending_question(documents["handoff"])
    topic_id = topic_ids["kafka"] if question and "kafka" in question.lower() else None
    conn.execute(
        """INSERT INTO learning_state (user_id, next_topic_id, next_question)
           VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING""",
        (user_id, topic_id, question),
    )

    for name, content in documents.items():
        row = conn.execute(
            "SELECT content, sha256 FROM learning_documents WHERE name = %s", (name,)
        ).fetchone()
        if row != (content, hashlib.sha256(content.encode("utf-8")).hexdigest()):
            raise ValueError(f"Verification failed for document {name}")
    imported = conn.execute(
        "SELECT COUNT(*) FROM learning_entries WHERE user_id = %s",
        (user_id,),
    ).fetchone()[0]
    if imported < len(entries):
        raise ValueError("Verification failed for S3 entries")
    sections = conn.execute("SELECT COUNT(*) FROM history_sections").fetchone()[0]
    if sections != len(history_sections(documents["history"])):
        raise ValueError("Verification failed for history sections")
    return len(documents), sections, imported


def main():
    dsn = os.environ["LEARNIKAL_DATABASE_URL"]
    bucket = os.environ["LEARNIKAL_S3_BUCKET"]
    username = os.getenv("LEARNIKAL_USERNAME", "kalin")
    documents, entries = read_source(boto3.client("s3"), bucket)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        counts = migrate(conn, documents, entries, username)
    print(f"Verified in PostgreSQL: {counts[0]} documents, {counts[1]} history sections, {counts[2]} entries")
    print("S3 was not modified.")


if __name__ == "__main__":
    main()
