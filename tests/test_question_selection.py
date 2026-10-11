import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from learnikal.models import Subtopic
from learnikal.question_selection import EmptyQuestionCatalogError, QuestionSelectionService


class Store:
    def __init__(self, subtopics, stats=None, difficulties=None):
        self.subtopics = subtopics
        self.stats = stats or {item.topic_id: (0, None) for item in subtopics}
        self.difficulties = difficulties or {item.id: [2] for item in subtopics}

    def topic_rating_stats(self, username=None):
        return self.stats

    def list_active_topic_subtopics(self, username=None, difficulty_ranges=None):
        return [item for item in self.subtopics if any(
            difficulty_ranges[item.topic_id][0] <= difficulty <= difficulty_ranges[item.topic_id][1]
            for difficulty in self.difficulties[item.id]
        )]

    def available_difficulties(self, username, subtopic_id, minimum, maximum):
        return [difficulty for difficulty in self.difficulties[subtopic_id]
                if minimum <= difficulty <= maximum]

    def select_question(self, username, subtopic_id, difficulty):
        return SimpleNamespace(id=1000 + subtopic_id, text=f"Question {subtopic_id}")


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
        self.assertEqual((selected.question_id, selected.text), (1021, "Question 21"))

    def test_rejects_invalid_initial_difficulty(self):
        with self.assertRaises(ValueError):
            QuestionSelectionService(Store([]), initial_difficulty=6)

    def test_uses_topic_average_after_ten_distinct_questions(self):
        item = subtopic(1, 11)
        store = Store([item], stats={1: (10, 3.1)}, difficulties={11: [1, 2, 3, 4, 5]})
        selected = QuestionSelectionService(store, choice=lambda values: values[-1]).select()
        self.assertEqual(selected.difficulty, 4)
        self.assertEqual(QuestionSelectionService(store).difficulty_range(10, 3.1), (2, 4))
        self.assertEqual(QuestionSelectionService(store).difficulty_range(10, 4.5), (3, 5))
        self.assertEqual(QuestionSelectionService(store).difficulty_range(9, 4.5), (2, 2))

    def test_does_not_fall_back_below_allowed_difficulty(self):
        item = subtopic(1, 11)
        store = Store([item], stats={1: (10, 4.5)}, difficulties={11: [2]})
        with self.assertRaises(EmptyQuestionCatalogError):
            QuestionSelectionService(store).select()


if __name__ == "__main__":
    unittest.main()
