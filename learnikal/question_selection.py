"""Selection of the topic, subtopic and difficulty for the next question."""

import secrets
from math import floor
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import TypeVar

from .models import NextQuestionContext, Subtopic


T = TypeVar("T")


class EmptyQuestionCatalogError(Exception):
    """No active topic has an active subtopic."""


class QuestionSelectionService:
    def __init__(
        self,
        store,
        *,
        choice: Callable[[Sequence[T]], T] = secrets.choice,
        initial_difficulty: int = 2,
    ):
        if not 1 <= initial_difficulty <= 5:
            raise ValueError("initial_difficulty must be between 1 and 5")
        self.store = store
        self.choice = choice
        self.initial_difficulty = initial_difficulty

    def difficulty_range(self, rated_questions: int, average_score: float | None) -> tuple[int, int]:
        if rated_questions < 10 or average_score is None:
            return self.initial_difficulty, self.initial_difficulty
        return max(1, floor(average_score - 1)), min(5, floor(average_score + 1))

    def select(self, username: str | None = None) -> NextQuestionContext:
        difficulty_ranges = {
            topic_id: self.difficulty_range(count, average)
            for topic_id, (count, average) in self.store.topic_rating_stats(username).items()
        }
        by_topic: dict[int, list[Subtopic]] = defaultdict(list)
        for subtopic in self.store.list_active_topic_subtopics(
            username=username, difficulty_ranges=difficulty_ranges
        ):
            by_topic[subtopic.topic_id].append(subtopic)
        if not by_topic:
            raise EmptyQuestionCatalogError

        # Choose the topic first so every topic has the same probability,
        # regardless of how many subtopics it contains.
        topic_id = self.choice(tuple(sorted(by_topic)))
        subtopic = self.choice(tuple(by_topic[topic_id]))
        minimum, maximum = difficulty_ranges[topic_id]
        available = self.store.available_difficulties(username, subtopic.id, minimum, maximum)
        if not available:
            raise EmptyQuestionCatalogError
        difficulty = self.choice(tuple(available))
        question = self.store.select_question(
            username=username,
            subtopic_id=subtopic.id,
            difficulty=difficulty,
        )
        if question is None:
            raise EmptyQuestionCatalogError
        return NextQuestionContext(
            question_id=question.id,
            text=question.text,
            topic_id=subtopic.topic_id,
            topic_name=subtopic.topic_name,
            subtopic_id=subtopic.id,
            subtopic_name=subtopic.name,
            difficulty=difficulty,
        )
