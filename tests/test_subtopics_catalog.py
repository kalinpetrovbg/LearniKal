import csv
import tempfile
import unittest
from collections import Counter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "deploy" / "import-subtopics-catalog.py"
spec = spec_from_file_location("import_subtopics_catalog", path)
catalog = module_from_spec(spec)
spec.loader.exec_module(catalog)


class SubtopicsCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = catalog.read_catalog(catalog.DEFAULT_CATALOG)
        cls.topics = {topic: index for index, topic in enumerate(sorted(catalog.TOPICS), 1)}

    def test_catalog_covers_all_topics_without_padding_or_duplicates(self):
        self.assertEqual(Counter(row.topic_slug for row in self.rows),
                         {topic: 55 for topic in catalog.TOPICS})

    def test_preserves_the_existing_catalog_keys(self):
        expected = {
            "ai": {"retrieval"},
            "airflow": {"fundamentals", "reliability"},
            "data_engineering": {"data_pipelines", "data_quality"},
            "design_patterns": {"behavioral", "creational", "fundamentals", "structural"},
            "kafka": {"consumers", "fundamentals"},
            "postgresql": {"performance", "querying", "transactions"},
            "python": {"concurrency", "fundamentals", "language_basics"},
            "redis": {"caching"},
            "rest_api": {"fundamentals", "pagination"},
            "testing": {"assertions"},
        }
        keys = {(row.topic_slug, row.subtopic_slug) for row in self.rows}
        self.assertTrue({(topic, slug) for topic, slugs in expected.items() for slug in slugs} <= keys)

    def test_rejects_duplicate_slug_or_case_insensitive_name(self):
        original = self.rows[0]
        variants = [original._replace(subtopic_name="Different name"),
                    original._replace(subtopic_slug="different_slug", subtopic_name=original.subtopic_name.upper())]
        for duplicate in variants:
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, "duplicate"):
                catalog.validate_catalog([*self.rows, duplicate])

    def test_rejects_missing_topics_and_insufficient_coverage(self):
        with self.assertRaisesRegex(ValueError, "missing="):
            catalog.validate_catalog([row for row in self.rows if row.topic_slug != "python"])
        with self.assertRaisesRegex(ValueError, "at least 50"):
            catalog.validate_catalog(self.rows[6:])

    def test_rejects_invalid_names_and_slugs(self):
        first = self.rows[0]
        variants = [first._replace(subtopic_slug="X" * 41),
                    first._replace(subtopic_name="  Whitespace"),
                    first._replace(subtopic_name="Line\nbreak"),
                    first._replace(subtopic_name="a" * 101)]
        for row in variants:
            with self.subTest(row=row), self.assertRaises(ValueError):
                catalog.validate_catalog([row, *self.rows[1:]])

    def test_csv_rejects_wrong_headers_and_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.csv"
            for lines in [["name,slug\n"],
                          [",".join(catalog.FIELDS) + "\n", "ai,models,Models,extra\n"]]:
                path.write_text("".join(lines), encoding="utf-8")
                with self.assertRaises(ValueError):
                    catalog.read_catalog(path)

    def test_csv_accepts_utf8_bom_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(catalog.FIELDS)
                writer.writerows(self.rows)
            self.assertEqual(catalog.read_catalog(path), self.rows)

    def test_plan_is_repeatable_and_preserves_unrelated_entries(self):
        existing = [tuple(row) for row in self.rows[:21]]
        existing.append(("python", "custom_topic", "Custom Topic"))
        pending = catalog.plan_import(self.rows, self.topics, iter(existing))
        self.assertEqual(pending, self.rows[21:])
        existing.extend(tuple(row) for row in pending)
        self.assertEqual(catalog.plan_import(self.rows, self.topics, existing), [])

    def test_plan_requires_topics_and_refuses_ambiguous_mappings(self):
        first = self.rows[0]
        with self.assertRaisesRegex(ValueError, "missing topics"):
            catalog.plan_import(self.rows, {}, [])
        with self.assertRaisesRegex(ValueError, "Name conflict"):
            catalog.plan_import(self.rows, self.topics,
                                [(first.topic_slug, first.subtopic_slug, "Other name")])
        with self.assertRaisesRegex(ValueError, "Slug conflict"):
            catalog.plan_import(self.rows, self.topics,
                                [(first.topic_slug, "other_slug", first.subtopic_name.upper())])


if __name__ == "__main__":
    unittest.main()
