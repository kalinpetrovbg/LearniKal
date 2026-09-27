"""Validate or add the curated catalog without altering existing subtopics.

Default: read-only database preview. Use --validate for CSV-only validation,
or --apply to commit all missing subtopics in one transaction.
"""

import argparse
import csv
import os
import re
from collections import Counter, namedtuple
from pathlib import Path


FIELDS = ("topic_slug", "subtopic_slug", "subtopic_name")
TOPICS = frozenset((
    "ai", "airflow", "clickhouse", "data_engineering", "design_patterns",
    "docker", "kafka", "pandas_polars", "postgresql", "python", "redis",
    "rest_api", "testing",
))
SLUG = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
DEFAULT_CATALOG = Path(__file__).with_name("subtopics-catalog.csv")
Entry = namedtuple("Entry", FIELDS)


def read_catalog(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(FIELDS):
            raise ValueError(f"Expected CSV columns: {', '.join(FIELDS)}")
        rows = []
        for line, values in enumerate(reader, 2):
            if None in values or any(values.get(field) is None for field in FIELDS):
                raise ValueError(f"CSV row {line}: wrong number of fields")
            rows.append(Entry(*(values[field] for field in FIELDS)))
    validate_catalog(rows)
    return rows


def validate_catalog(rows):
    slugs, names = set(), set()
    counts = Counter()
    for line, row in enumerate(rows, 2):
        if any(not value or value != value.strip() for value in row):
            raise ValueError(f"CSV row {line}: empty value or surrounding whitespace")
        if not SLUG.fullmatch(row.topic_slug) or not SLUG.fullmatch(row.subtopic_slug):
            raise ValueError(f"CSV row {line}: invalid slug (maximum 40 characters)")
        if len(row.subtopic_name) > 100 or any(ord(c) < 32 for c in row.subtopic_name):
            raise ValueError(f"CSV row {line}: invalid subtopic name")
        slug_key = (row.topic_slug, row.subtopic_slug)
        name_key = (row.topic_slug, row.subtopic_name.casefold())
        if slug_key in slugs or name_key in names:
            raise ValueError(f"CSV row {line}: duplicate subtopic in {row.topic_slug}")
        slugs.add(slug_key)
        names.add(name_key)
        counts[row.topic_slug] += 1
    if set(counts) != TOPICS:
        raise ValueError(f"Expected the 13 supported topics; missing={sorted(TOPICS - set(counts))}, "
                         f"unknown={sorted(set(counts) - TOPICS)}")
    for topic, count in counts.items():
        if count < 50:
            raise ValueError(f"Topic {topic} requires at least 50 subtopics; found {count}")


def plan_import(rows, topics, existing):
    """Return only absent entries; never rename, reactivate or remap existing IDs.

    topics: mapping slug -> ID. existing: iterable (topic_slug, slug, name).
    Conflicting names/slugs require an explicit decision, not an automatic merge.
    """
    missing_topics = {row.topic_slug for row in rows} - topics.keys()
    if missing_topics:
        raise ValueError(f"Database is missing topics: {', '.join(sorted(missing_topics))}")
    existing = list(existing)
    by_slug = {(topic, slug): name for topic, slug, name in existing}
    by_name = {(topic, name.casefold()): slug for topic, slug, name in existing}
    pending = []
    for row in rows:
        old_name = by_slug.get((row.topic_slug, row.subtopic_slug))
        old_slug = by_name.get((row.topic_slug, row.subtopic_name.casefold()))
        if old_name is not None:
            if old_name.casefold() != row.subtopic_name.casefold():
                raise ValueError(f"Name conflict for {row.topic_slug}/{row.subtopic_slug}: {old_name!r}")
        elif old_slug is not None:
            raise ValueError(f"Slug conflict for {row.topic_slug}/{row.subtopic_name}: {old_slug!r}")
        else:
            pending.append(row)
    return pending


def import_catalog(conn, rows, *, apply=False):
    """Use the caller's transaction and search_path; this function never commits."""
    validate_catalog(rows)
    if apply:
        # Serialize planning and inserts; ordinary reads can continue.
        conn.execute("LOCK TABLE topics, subtopics IN SHARE ROW EXCLUSIVE MODE")
    topics = dict(conn.execute("SELECT slug, id FROM topics").fetchall())
    existing = conn.execute(
        "SELECT t.slug, s.slug, s.name FROM subtopics s JOIN topics t ON t.id = s.topic_id"
    ).fetchall()
    pending = plan_import(rows, topics, existing)
    if apply:
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO subtopics (topic_id, slug, name) VALUES (%s, %s, %s)",
                [(topics[row.topic_slug], row.subtopic_slug, row.subtopic_name) for row in pending],
            )
    return Counter(row.topic_slug for row in pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true", help="Validate CSV without connecting to PostgreSQL")
    mode.add_argument("--dry-run", action="store_true", help="Read-only database preview (default)")
    mode.add_argument("--apply", action="store_true", help="Insert missing subtopics atomically")
    args = parser.parse_args()
    try:
        rows = read_catalog(args.catalog)
        counts = Counter(row.topic_slug for row in rows)
        if args.validate:
            print(f"Validated {len(rows)} subtopics across {len(counts)} topics")
            for topic, count in sorted(counts.items()):
                print(f"  {topic}: {count}")
            return

        import psycopg

        dsn = os.environ.get("LEARNIKAL_DATABASE_URL", "dbname=learnikal user=postgres")
        with psycopg.connect(dsn) as conn:
            if not args.apply:
                conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL search_path = public")
            conn.execute("SET LOCAL lock_timeout = '10s'")
            conn.execute("SET LOCAL statement_timeout = '60s'")
            pending = import_catalog(conn, rows, apply=args.apply)
        action = "Inserted" if args.apply else "Would insert"
        print(f"{action} {sum(pending.values())}; already present {len(rows) - sum(pending.values())}")
        for topic, count in sorted(counts.items()):
            print(f"  {topic}: {pending[topic]} new, {count - pending[topic]} already present")
    except ValueError as exc:
        parser.exit(1, f"Catalog rejected: {exc}\n")


if __name__ == "__main__":
    main()
