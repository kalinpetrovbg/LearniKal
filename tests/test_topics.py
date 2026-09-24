import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "deploy" / "migrate-topics.py"
spec = spec_from_file_location("migrate_topics", path)
module = module_from_spec(spec)
spec.loader.exec_module(module)


class TopicCatalogTests(unittest.TestCase):
    def test_catalog_contains_current_topics_and_display_names(self):
        self.assertEqual(len(module.TOPIC_NAMES), 13)
        self.assertEqual(module.TOPIC_NAMES["ai"], "AI")
        self.assertEqual(module.TOPIC_NAMES["postgresql"], "PostgreSQL")
        self.assertEqual(module.TOPIC_NAMES["rest_api"], "REST API")
        self.assertNotIn("ai_rag", module.TOPIC_NAMES)


if __name__ == "__main__":
    unittest.main()
