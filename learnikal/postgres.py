import re

import psycopg
from argon2 import PasswordHasher, Type
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import (
    Entry, EntryPage, Instruction, InstructionInput, InstructionUpdate, StartContext,
    Subtopic, SubtopicInput, SubtopicUpdate, Topic, TopicInput, TopicProgress,
    TopicUpdate, User, UserInput, UserUpdate,
)


DOCUMENTS = {
    "plan": "TEAM_LEAD_LEARNING_PLAN.md",
    "knowledge": "LEARNING_KNOWLEDGE_SUMMARY.md",
    "handoff": "learning_handoff.md",
    "history": "LEARNING_HISTORY.md",
    "patterns": "design_patterns.md",
}

DEFAULT_INSTRUCTIONS = [
    "Обучение за Python/Data Engineering Team Lead на български.",
    "Без код по подразбиране.",
    "Задавай по един кратък сценарий за архитектурна преценка, trade-offs, диагностика, коректност, производителност или design review.",
    "Всички технологии са равнопоставени.",
    "Редувай темите и не повтаряй наскоро проверени сценарии.",
    "Дай възможност за самостоятелен отговор преди подсказки.",
    "След отговора отдели показаното самостоятелно от изясненото с помощ и от непровереното.",
    "Прочетено обяснение не доказва усвоено знание.",
    "Не следи учебно време.",
]
STUDY_RULES = " ".join(DEFAULT_INSTRUCTIONS)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class TopicConflictError(Exception):
    pass


class TopicInUseError(Exception):
    pass


class SubtopicConflictError(Exception):
    pass


class UserConflictError(Exception):
    pass


class StorageError(Exception):
    pass


PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)


class PostgresStore:
    def __init__(self, dsn: str, username: str):
        self.dsn = dsn
        self.username = username

    def _connect(self):
        try:
            return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL connection failed") from exc

    def _user_id(self, conn):
        row = conn.execute("SELECT id FROM users WHERE username = %s", (self.username,)).fetchone()
        if row is None:
            raise StorageError("Learning user is not initialized")
        return row["id"]

    @staticmethod
    def _entry(row):
        return Entry(
            entry_id=row["id"], technology=row["technology"], question=row["question"],
            answer=row["answer"], evaluation=row["evaluation"], next_question=row["next_question"],
            difficulty=row["difficulty"], score=row["score"], created_at=row["created_at"],
        )

    @staticmethod
    def _topic(row):
        return Topic(
            id=row["id"], slug=row["slug"], name=row["name"],
            is_active=row["is_active"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _user(row):
        return User(
            id=row["id"], username=row["username"], first_name=row["first_name"],
            last_name=row["last_name"], email=row["email"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _instruction(row):
        return Instruction(
            id=row["id"], text=row["text"], position=row["position"],
            is_active=row["is_active"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _subtopic(row):
        return Subtopic(
            id=row["id"], topic_id=row["topic_id"], topic_slug=row["topic_slug"],
            topic_name=row["topic_name"], slug=row["slug"], name=row["name"],
            is_active=row["is_active"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def ping(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL health check failed") from exc

    def get_document(self, name: str) -> str:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT content FROM learning_documents WHERE name = %s", (name,)
                ).fetchone()
                if row is None:
                    raise NotFoundError
                return row["content"]
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def save_entry(self, entry: Entry) -> Entry:
        try:
            with self._connect() as conn:
                user_id = self._user_id(conn)
                topic = conn.execute(
                    "SELECT id FROM topics WHERE slug = %s AND is_active = true",
                    (entry.technology,),
                ).fetchone()
                if topic is None:
                    raise NotFoundError
                values = (user_id, topic["id"], entry.question, entry.answer,
                          Jsonb(entry.evaluation.model_dump()) if entry.evaluation else None,
                          entry.next_question, entry.difficulty, entry.score, entry.created_at)
                if entry.entry_id:
                    inserted = conn.execute(
                        """INSERT INTO learning_entries
                           (id, user_id, topic_id, question, answer, evaluation, next_question,
                            difficulty, score, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (id) DO NOTHING RETURNING id""",
                        (entry.entry_id, *values),
                    ).fetchone()
                else:
                    inserted = conn.execute(
                        """INSERT INTO learning_entries
                           (user_id, topic_id, question, answer, evaluation, next_question,
                            difficulty, score, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           RETURNING id""",
                        values,
                    ).fetchone()
                if inserted is None:
                    existing = self._get_entry(conn, user_id, entry.technology, entry.entry_id)
                    if existing.model_dump(exclude={"created_at"}) != entry.model_dump(exclude={"created_at"}):
                        raise ConflictError
                    return existing
                conn.execute(
                    """INSERT INTO learning_state (user_id, next_topic_id, next_question)
                       VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET
                       next_topic_id = EXCLUDED.next_topic_id,
                       next_question = EXCLUDED.next_question, updated_at = now()""",
                    (user_id, topic["id"] if entry.next_question else None, entry.next_question),
                )
                return Entry(**entry.model_dump(exclude={"entry_id"}), entry_id=inserted["id"])
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def create_topic(self, topic: TopicInput) -> Topic:
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """INSERT INTO topics (slug, name, is_active) VALUES (%s, %s, %s)
                           RETURNING id, slug, name, is_active, created_at, updated_at""",
                        (topic.slug, topic.name, topic.is_active),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise TopicConflictError from exc
                return self._topic(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def list_topics(self) -> list[Topic]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, slug, name, is_active, created_at, updated_at
                       FROM topics ORDER BY id"""
                ).fetchall()
                return [self._topic(row) for row in rows]
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def update_topic(self, topic_id: int, topic: TopicUpdate) -> Topic:
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """UPDATE topics SET
                           slug = COALESCE(%s, slug),
                           name = COALESCE(%s, name),
                           is_active = COALESCE(%s, is_active)
                           WHERE id = %s
                           RETURNING id, slug, name, is_active, created_at, updated_at""",
                        (topic.slug, topic.name, topic.is_active, topic_id),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise TopicConflictError from exc
                if row is None:
                    raise NotFoundError
                return self._topic(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def delete_topic(self, topic_id: int) -> None:
        try:
            with self._connect() as conn:
                topic = conn.execute("SELECT id FROM topics WHERE id = %s", (topic_id,)).fetchone()
                if topic is None:
                    raise NotFoundError
                entry_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_entries WHERE topic_id = %s",
                    (topic_id,),
                ).fetchone()["count"]
                if entry_count:
                    raise TopicInUseError
                conn.execute(
                    "UPDATE learning_state SET next_topic_id = NULL WHERE next_topic_id = %s",
                    (topic_id,),
                )
                conn.execute("DELETE FROM topics WHERE id = %s", (topic_id,))
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def create_subtopic(self, subtopic: SubtopicInput) -> Subtopic:
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """INSERT INTO subtopics (topic_id, slug, name, is_active)
                           VALUES (%s, %s, %s, %s)
                           RETURNING id, topic_id, slug, name, is_active, created_at, updated_at""",
                        (subtopic.topic_id, subtopic.slug, subtopic.name, subtopic.is_active),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise SubtopicConflictError from exc
                except psycopg.errors.ForeignKeyViolation as exc:
                    raise NotFoundError from exc
                return self._subtopic(self._with_topic(conn, row))
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def list_subtopics(self) -> list[Subtopic]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT s.id, s.topic_id, t.slug AS topic_slug, t.name AS topic_name,
                              s.slug, s.name, s.is_active, s.created_at, s.updated_at
                       FROM subtopics s JOIN topics t ON t.id = s.topic_id
                       ORDER BY s.topic_id, s.id"""
                ).fetchall()
                return [self._subtopic(row) for row in rows]
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def update_subtopic(self, subtopic_id: int, subtopic: SubtopicUpdate) -> Subtopic:
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """UPDATE subtopics SET
                           topic_id = COALESCE(%s, topic_id),
                           slug = COALESCE(%s, slug),
                           name = COALESCE(%s, name),
                           is_active = COALESCE(%s, is_active)
                           WHERE id = %s
                           RETURNING id, topic_id, slug, name, is_active, created_at, updated_at""",
                        (
                            subtopic.topic_id, subtopic.slug, subtopic.name,
                            subtopic.is_active, subtopic_id,
                        ),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise SubtopicConflictError from exc
                except psycopg.errors.ForeignKeyViolation as exc:
                    raise NotFoundError from exc
                if row is None:
                    raise NotFoundError
                return self._subtopic(self._with_topic(conn, row))
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def delete_subtopic(self, subtopic_id: int) -> None:
        try:
            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM subtopics WHERE id = %s RETURNING id",
                    (subtopic_id,),
                ).fetchone()
                if deleted is None:
                    raise NotFoundError
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def _with_topic(self, conn, subtopic_row):
        row = conn.execute(
            """SELECT s.id, s.topic_id, t.slug AS topic_slug, t.name AS topic_name,
                      s.slug, s.name, s.is_active, s.created_at, s.updated_at
               FROM subtopics s JOIN topics t ON t.id = s.topic_id WHERE s.id = %s""",
            (subtopic_row["id"],),
        ).fetchone()
        if row is None:
            raise NotFoundError
        return row

    def create_user(self, user: UserInput) -> User:
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """INSERT INTO users
                           (username, first_name, last_name, email, password_hash)
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id, username, first_name, last_name, email, created_at, updated_at""",
                        (
                            user.username, user.first_name, user.last_name, user.email,
                            PASSWORD_HASHER.hash(user.password),
                        ),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise UserConflictError from exc
                return self._user(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def list_users(self) -> list[User]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, username, first_name, last_name, email, created_at, updated_at
                       FROM users ORDER BY id"""
                ).fetchall()
                return [self._user(row) for row in rows]
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def update_user(self, user_id: int, user: UserUpdate) -> User:
        password_hash = PASSWORD_HASHER.hash(user.password) if user.password is not None else None
        try:
            with self._connect() as conn:
                try:
                    row = conn.execute(
                        """UPDATE users SET
                           username = COALESCE(%s, username),
                           first_name = COALESCE(%s, first_name),
                           last_name = COALESCE(%s, last_name),
                           email = COALESCE(%s, email),
                           password_hash = COALESCE(%s, password_hash)
                           WHERE id = %s
                           RETURNING id, username, first_name, last_name, email, created_at, updated_at""",
                        (
                            user.username, user.first_name, user.last_name, user.email,
                            password_hash, user_id,
                        ),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise UserConflictError from exc
                if row is None:
                    raise NotFoundError
                return self._user(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def delete_user(self, user_id: int) -> None:
        try:
            with self._connect() as conn:
                user = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
                if user is None:
                    raise NotFoundError
                conn.execute("DELETE FROM learning_state WHERE user_id = %s", (user_id,))
                conn.execute("DELETE FROM learning_entries WHERE user_id = %s", (user_id,))
                conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def create_instruction(self, instruction: InstructionInput) -> Instruction:
        try:
            with self._connect() as conn:
                position = instruction.position
                if position is None:
                    row = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS position FROM instructions").fetchone()
                    position = row["position"]
                row = conn.execute(
                    """INSERT INTO instructions (text, position, is_active)
                       VALUES (%s, %s, %s)
                       RETURNING id, text, position, is_active, created_at, updated_at""",
                    (instruction.text, position, instruction.is_active),
                ).fetchone()
                return self._instruction(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def list_instructions(self) -> list[Instruction]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, text, position, is_active, created_at, updated_at
                       FROM instructions ORDER BY position, id"""
                ).fetchall()
                return [self._instruction(row) for row in rows]
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def update_instruction(self, instruction_id: int, instruction: InstructionUpdate) -> Instruction:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """UPDATE instructions SET
                       text = COALESCE(%s, text),
                       position = COALESCE(%s, position),
                       is_active = COALESCE(%s, is_active)
                       WHERE id = %s
                       RETURNING id, text, position, is_active, created_at, updated_at""",
                    (instruction.text, instruction.position, instruction.is_active, instruction_id),
                ).fetchone()
                if row is None:
                    raise NotFoundError
                return self._instruction(row)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def delete_instruction(self, instruction_id: int) -> None:
        try:
            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM instructions WHERE id = %s RETURNING id",
                    (instruction_id,),
                ).fetchone()
                if deleted is None:
                    raise NotFoundError
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL write failed") from exc

    def _get_entry(self, conn, user_id, technology, entry_id):
        row = conn.execute(
            """SELECT e.*, t.slug AS technology FROM learning_entries e
               JOIN topics t ON t.id = e.topic_id
               WHERE e.id = %s AND e.user_id = %s AND t.slug = %s""",
            (entry_id, user_id, technology),
        ).fetchone()
        if row is None:
            raise NotFoundError
        return self._entry(row)

    def get_entry(self, technology: str, entry_id: int) -> Entry:
        try:
            with self._connect() as conn:
                return self._get_entry(conn, self._user_id(conn), technology, entry_id)
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def list_entries(self, technology: str, limit: int, cursor: int) -> EntryPage:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT e.*, t.slug AS technology FROM learning_entries e
                       JOIN topics t ON t.id = e.topic_id
                       WHERE e.user_id = %s AND t.slug = %s
                       ORDER BY e.created_at DESC, e.id DESC LIMIT %s OFFSET %s""",
                    (self._user_id(conn), technology, limit + 1, cursor),
                ).fetchall()
                return EntryPage(
                    items=[self._entry(row) for row in rows[:limit]],
                    next_cursor=str(cursor + limit) if len(rows) > limit else None,
                )
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc

    def start(self) -> StartContext:
        try:
            with self._connect() as conn:
                user_id = self._user_id(conn)
                instruction_rows = conn.execute(
                    """SELECT text FROM instructions WHERE is_active = true
                       ORDER BY position, id"""
                ).fetchall()
                if not instruction_rows:
                    raise StorageError("Learning instructions are not initialized")
                knowledge = conn.execute(
                    "SELECT content FROM learning_documents WHERE name = 'knowledge'"
                ).fetchone()
                state = conn.execute(
                    """SELECT s.next_question, t.slug AS next_topic FROM learning_state s
                       LEFT JOIN topics t ON t.id = s.next_topic_id AND t.is_active = true
                       WHERE s.user_id = %s""",
                    (user_id,),
                ).fetchone()
                topic = conn.execute(
                    """SELECT t.slug FROM topics t
                       LEFT JOIN learning_entries e ON e.topic_id = t.id AND e.user_id = %s
                       WHERE t.is_active = true
                       GROUP BY t.id, t.slug
                       ORDER BY max(e.created_at) ASC NULLS FIRST, t.slug ASC LIMIT 1""",
                    (user_id,),
                ).fetchone()
                progress_rows = conn.execute(
                    """SELECT t.slug, COUNT(e.id) AS answer_count,
                              AVG(e.score) AS average_score
                       FROM topics t LEFT JOIN learning_entries e
                         ON e.topic_id = t.id AND e.user_id = %s
                       WHERE t.is_active = true
                       GROUP BY t.id, t.slug ORDER BY t.slug""",
                    (user_id,),
                ).fetchall()
                summary = knowledge["content"] if knowledge else None
                if summary:
                    summary = re.split(r"(?m)^## Текуща посока\s*$", summary)[0].strip()
                return StartContext(
                    instructions="\n".join(row["text"] for row in instruction_rows),
                    knowledge_summary=summary,
                    suggested_technology=(state["next_topic"] if state and state["next_question"] else None)
                    or (topic["slug"] if topic else None),
                    next_question=state["next_question"] if state else None,
                    topic_progress=[TopicProgress(
                        technology=row["slug"], answer_count=row["answer_count"],
                        average_score=float(row["average_score"]) if row["average_score"] is not None else None,
                    ) for row in progress_rows],
                )
        except psycopg.Error as exc:
            raise StorageError("PostgreSQL read failed") from exc
