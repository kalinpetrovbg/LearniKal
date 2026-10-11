"""Selection of the topic, subtopic and difficulty for the next question."""

import secrets
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

    def select(self, username: str | None = None) -> NextQuestionContext:
        by_topic: dict[int, list[Subtopic]] = defaultdict(list)
        for subtopic in self.store.list_active_topic_subtopics(username=username):
            by_topic[subtopic.topic_id].append(subtopic)
        if not by_topic:
            raise EmptyQuestionCatalogError

        # Choose the topic first so every topic has the same probability,
        # regardless of how many subtopics it contains.
        topic_id = self.choice(tuple(sorted(by_topic)))
        subtopic = self.choice(tuple(by_topic[topic_id]))
        question = self.store.select_question(
            username=username,
            subtopic_id=subtopic.id,
            difficulty=self.initial_difficulty,
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
            difficulty=self.initial_difficulty,
        )
