import unittest
from datetime import datetime, timezone

from learnikal.models import Subtopic
from learnikal.question_selection import QuestionSelectionService


class Store:
    def __init__(self, subtopics):
        self.subtopics = subtopics

    def list_active_topic_subtopics(self):
        return self.subtopics


def subtopic(topic_id, subtopic_id):
    now = datetime.now(timezone.utc)
    return Subtopic(
        id=subtopic_id,
        topic_id=topic_id,
        topic_slug=f"topic_{topic_id}",
        topic_name=f"Topic {topic_id}",
        slug=f"subtopic_{subtopic_id}",
        name=f"Subtopic {subtopic_id}",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class QuestionSelectionTests(unittest.TestCase):
    def test_selects_topic_before_subtopic(self):
        populations = []

        def choose_last(values):
            populations.append(tuple(values))
            return values[-1]

        selected = QuestionSelectionService(
            Store([subtopic(1, 11), subtopic(1, 12), subtopic(2, 21)]),
            choice=choose_last,
        ).select()

        self.assertEqual(populations[0], (1, 2))
        self.assertEqual([item.id for item in populations[1]], [21])
        self.assertEqual((selected.topic_id, selected.subtopic_id, selected.difficulty), (2, 21, 2))

    def test_rejects_invalid_initial_difficulty(self):
        with self.assertRaises(ValueError):
            QuestionSelectionService(Store([]), initial_difficulty=6)


if __name__ == "__main__":
    unittest.main()
