from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Evaluation(BaseModel):
    demonstrated_independently: str | None = None
    clarified_with_help: str | None = None
    remaining_unverified: str | None = None


class EntryInput(BaseModel):
    technology: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    question: str = Field(min_length=1, max_length=20000)
    answer: str = Field(min_length=1, max_length=50000)
    evaluation: Evaluation | None = None
    next_question: str | None = None
    difficulty: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    score: int | None = Field(default=None, ge=0, le=5)
    entry_id: int | None = Field(default=None, ge=1)

    @field_validator("technology")
    @classmethod
    def normalize_technology(cls, value: str) -> str:
        return value.lower()

    @field_validator("question", "answer")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must contain non-whitespace text")
        return value


class Entry(EntryInput):
    created_at: datetime


class EntryPage(BaseModel):
    items: list[Entry]
    next_cursor: str | None = None


class TopicInput(BaseModel):
    slug: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value


class Topic(TopicInput):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class Document(BaseModel):
    name: str
    content: str


class StartContext(BaseModel):
    instructions: str
    knowledge_summary: str | None
    suggested_technology: str | None
    next_question: str | None
    topic_progress: list["TopicProgress"] = Field(default_factory=list)


class TopicProgress(BaseModel):
    technology: str
    answer_count: int
    average_score: float | None
