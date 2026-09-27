import unittest

from migrate_s3 import history_sections


class MigrationParsingTests(unittest.TestCase):
    def test_history_sections_keep_content(self):
        sections = history_sections("# Title\n### First\nAnswer one\n### Second\nAnswer two\n")
        self.assertEqual(sections, [(0, "First", "Answer one"), (1, "Second", "Answer two")])

