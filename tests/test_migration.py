import unittest

from migrate_s3 import history_sections, pending_question


class MigrationParsingTests(unittest.TestCase):
    def test_history_sections_keep_content(self):
        sections = history_sections("# Title\n### First\nAnswer one\n### Second\nAnswer two\n")
        self.assertEqual(sections, [(0, "First", "Answer one"), (1, "Second", "Answer two")])

    def test_pending_question_ignores_followup_instructions(self):
        content = "## Следващ въпрос\n\nКак избираш key?\n\nБез код. След отговора запиши.\n\n## След отговора\n"
        self.assertEqual(pending_question(content), "Как избираш key?")
