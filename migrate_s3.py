"""One-time, repeatable import from the old S3 store into PostgreSQL."""

import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4

import boto3
import psycopg

from learnikal.models import Entry
from learnikal.postgres import DOCUMENTS, STUDY_RULES


TOPICS = (
    "airflow", "ai_rag", "clickhouse", "data_engineering", "design_patterns",
    "docker", "kafka", "pandas_polars", "postgresql", "python", "redis",
    "rest_api", "testing",
)


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
            entry = Entry.model_validate_json(body)
            expected_key = f"learning/entries/{entry.technology}/{entry.entry_id}.json"
            if item["Key"] != expected_key:
                raise ValueError(f"S3 entry key does not match content: {item['Key']}")
            entries.append(entry)
    if len({entry.entry_id for entry in entries}) != len(entries):
        raise ValueError("Duplicate entry IDs in S3")
    return documents, entries


def migrate(conn, documents, entries, username):
    conn.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO users (id, username) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
        (uuid4(), username),
    )
    user_id = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_policy (id, instructions) VALUES (true, %s) ON CONFLICT (id) DO NOTHING",
        (STUDY_RULES,),
    )

    for slug in sorted(set(TOPICS) | {entry.technology for entry in entries}):
        conn.execute("INSERT INTO topics (slug) VALUES (%s) ON CONFLICT DO NOTHING", (slug,))
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

    for entry in entries:
        from psycopg.types.json import Jsonb

        existing = conn.execute(
            """SELECT user_id, topic_id, question, answer, evaluation, next_question,
                      difficulty, score, created_at FROM learning_entries WHERE id = %s""",
            (entry.entry_id,),
        ).fetchone()
        if existing:
            expected = (
                user_id, topic_ids[entry.technology], entry.question, entry.answer,
                entry.evaluation.model_dump() if entry.evaluation else None,
                entry.next_question, entry.difficulty, entry.score, entry.created_at,
            )
            if existing != expected:
                raise ValueError(f"PostgreSQL entry {entry.entry_id} differs from S3")
            continue
        conn.execute(
            """INSERT INTO learning_entries
               (id, user_id, topic_id, question, answer, evaluation, next_question,
                difficulty, score, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (entry.entry_id, user_id, topic_ids[entry.technology], entry.question,
             entry.answer, Jsonb(entry.evaluation.model_dump()) if entry.evaluation else None,
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
    ids = [entry.entry_id for entry in entries]
    imported = conn.execute(
        "SELECT COUNT(*) FROM learning_entries WHERE user_id = %s AND id = ANY(%s)",
        (user_id, ids),
    ).fetchone()[0]
    if imported != len(entries):
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
