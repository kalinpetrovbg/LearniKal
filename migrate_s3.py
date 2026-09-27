"""One-time, repeatable import from the old S3 store into PostgreSQL."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import boto3
import psycopg
from pydantic import BaseModel, Field, field_validator

from learnikal.postgres import DEFAULT_INSTRUCTIONS


DOCUMENTS = {
    "plan": "TEAM_LEAD_LEARNING_PLAN.md",
    "knowledge": "LEARNING_KNOWLEDGE_SUMMARY.md",
    "handoff": "learning_handoff.md",
    "history": "LEARNING_HISTORY.md",
    "patterns": "design_patterns.md",
}


class LegacyEntry(BaseModel):
    technology: str
    question: str
    answer: str
    evaluation: dict | None = None
    difficulty: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    score: int | None = Field(default=None, ge=0, le=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("technology")
    @classmethod
    def normalize_technology(cls, value: str) -> str:
        return value.lower()


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
            entry = LegacyEntry.model_validate(raw_entry)
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
    for position, text in enumerate(DEFAULT_INSTRUCTIONS, start=1):
        conn.execute(
            """INSERT INTO instructions (text, position)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (text, position),
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
        existing = conn.execute(
            'SELECT text FROM instructions WHERE "type" = %s AND is_active = true '
            'ORDER BY position, id LIMIT 1',
            (name,),
        ).fetchone()
        if existing and existing[0] != content:
            raise ValueError(f"PostgreSQL document {name} differs from S3; refusing overwrite")
        if not existing:
            conn.execute(
                '''INSERT INTO instructions ("type", text, position, is_active)
                   VALUES (%s, %s, 1, true)''',
                (name, content),
            )

    for _legacy_id, entry in entries:
        existing = conn.execute(
            """SELECT id FROM answers
               WHERE user_id = %s AND topic_id = %s AND created_at = %s""",
            (user_id, topic_ids[entry.technology], entry.created_at),
        ).fetchone()
        if existing:
            continue
        difficulty = {"low": 1, "medium": 3, "high": 5}.get(entry.difficulty or "medium", 3)
        score = entry.score if entry.score is not None else 0
        metric = min(5, max(1, score or 3))
        conn.execute(
            """INSERT INTO answers
               (user_id, topic_id, question_id, score, difficulty, independence_score,
                clarity_score, completeness_score, confidence_score, created_at)
               VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, topic_ids[entry.technology], score, difficulty, metric, metric, metric, metric, entry.created_at),
        )

    for name, content in documents.items():
        row = conn.execute(
            'SELECT text FROM instructions WHERE "type" = %s AND is_active = true '
            'ORDER BY position, id LIMIT 1',
            (name,),
        ).fetchone()
        if row is None or row[0] != content:
            raise ValueError(f"Verification failed for document {name}")
    imported = conn.execute(
        "SELECT COUNT(*) FROM answers WHERE user_id = %s",
        (user_id,),
    ).fetchone()[0]
    if imported < len(entries):
        raise ValueError("Verification failed for S3 entries")
    return len(documents), imported


def main():
    dsn = os.environ["LEARNIKAL_DATABASE_URL"]
    bucket = os.environ["LEARNIKAL_S3_BUCKET"]
    username = os.getenv("LEARNIKAL_USERNAME", "kalin")
    documents, entries = read_source(boto3.client("s3"), bucket)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        counts = migrate(conn, documents, entries, username)
    print(f"Verified in PostgreSQL: {counts[0]} documents, {counts[1]} entries")
    print("S3 was not modified.")


if __name__ == "__main__":
    main()
