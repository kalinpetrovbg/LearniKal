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

    def select(self) -> NextQuestionContext:
        by_topic: dict[int, list[Subtopic]] = defaultdict(list)
        for subtopic in self.store.list_active_topic_subtopics():
            by_topic[subtopic.topic_id].append(subtopic)
        if not by_topic:
            raise EmptyQuestionCatalogError

        # Choose the topic first so every topic has the same probability,
        # regardless of how many subtopics it contains.
        topic_id = self.choice(tuple(sorted(by_topic)))
        subtopic = self.choice(tuple(by_topic[topic_id]))
        return NextQuestionContext(
            topic_id=subtopic.topic_id,
            topic_slug=subtopic.topic_slug,
            topic_name=subtopic.topic_name,
            subtopic_id=subtopic.id,
            subtopic_slug=subtopic.slug,
            subtopic_name=subtopic.name,
            difficulty=self.initial_difficulty,
        )
