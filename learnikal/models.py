from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class AnswerInput(BaseModel):
    id: int | None = Field(default=None, ge=1)
    user_id: int | None = Field(default=None, ge=1)
    topic_id: int = Field(ge=1)
    subtopic_id: int | None = Field(default=None, ge=1)
    question_id: int | None = Field(default=None, ge=1)
    score: int = Field(ge=0, le=5)
    difficulty: int = Field(ge=1, le=5)
    independence_score: int = Field(ge=1, le=5)
    clarity_score: int = Field(ge=1, le=5)
    completeness_score: int = Field(ge=1, le=5)
    confidence_score: int = Field(ge=1, le=5)


class Answer(AnswerInput):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class AnswerPage(BaseModel):
    items: list[Answer]
    next_cursor: str | None = None


class TopicInput(BaseModel):
    slug: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True

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


class TopicUpdate(BaseModel):
    slug: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one topic field must be provided")
        return self


class Topic(TopicInput):
    id: int
    created_at: datetime
    updated_at: datetime


class SubtopicInput(BaseModel):
    topic_id: int = Field(ge=1)
    slug: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True

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


class SubtopicUpdate(BaseModel):
    topic_id: int | None = Field(default=None, ge=1)
    slug: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one subtopic field must be provided")
        return self


class Subtopic(SubtopicInput):
    id: int
    topic_slug: str
    topic_name: str
    created_at: datetime
    updated_at: datetime


class InstructionInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    position: int | None = Field(default=None, ge=1)
    is_active: bool = True

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value


class InstructionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=5000)
    position: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one instruction field must be provided")
        return self


class Instruction(InstructionInput):
    id: int
    created_at: datetime
    updated_at: datetime


class UserInput(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,39}$")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("first_name", "last_name", "email", "password")
    @classmethod
    def reject_blank_profile_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,39}$")
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    password: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else value

    @field_validator("first_name", "last_name", "email", "password")
    @classmethod
    def reject_blank_profile_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must contain non-whitespace text")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else value

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one user field must be provided")
        return self


class User(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
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
