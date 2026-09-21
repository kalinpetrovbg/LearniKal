import re

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Entry, EntryPage, StartContext, TopicProgress


DOCUMENTS = {
    "plan": "TEAM_LEAD_LEARNING_PLAN.md",
    "knowledge": "LEARNING_KNOWLEDGE_SUMMARY.md",
    "handoff": "learning_handoff.md",
    "history": "LEARNING_HISTORY.md",
    "patterns": "design_patterns.md",
}

STUDY_RULES = (
    "Обучение за Python/Data Engineering Team Lead на български, без код по подразбиране. "
    "Задавай по един кратък сценарий за архитектурна преценка, trade-offs, диагностика, "
    "коректност, производителност или design review. Всички технологии са равнопоставени. "
    "Редувай темите и не повтаряй наскоро проверени сценарии. Дай възможност за "
    "самостоятелен отговор преди подсказки. След отговора отдели показаното самостоятелно "
    "от изясненото с помощ и от непровереното. Прочетено обяснение не доказва усвоено "
    "знание. Не следи учебно време."
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class StorageError(Exception):
    pass


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
                    "INSERT INTO topics (slug) VALUES (%s) "
                    "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id",
                    (entry.technology,),
                ).fetchone()
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
                policy = conn.execute(
                    "SELECT instructions FROM learning_policy WHERE id = true"
                ).fetchone()
                if policy is None:
                    raise StorageError("Learning policy is not initialized")
                knowledge = conn.execute(
                    "SELECT content FROM learning_documents WHERE name = 'knowledge'"
                ).fetchone()
                state = conn.execute(
                    """SELECT s.next_question, t.slug AS next_topic FROM learning_state s
                       LEFT JOIN topics t ON t.id = s.next_topic_id WHERE s.user_id = %s""",
                    (user_id,),
                ).fetchone()
                topic = conn.execute(
                    """SELECT t.slug FROM topics t
                       LEFT JOIN learning_entries e ON e.topic_id = t.id AND e.user_id = %s
                       GROUP BY t.id, t.slug
                       ORDER BY max(e.created_at) ASC NULLS FIRST, t.slug ASC LIMIT 1""",
                    (user_id,),
                ).fetchone()
                progress_rows = conn.execute(
                    """SELECT t.slug, COUNT(e.id) AS answer_count,
                              AVG(e.score) AS average_score
                       FROM topics t LEFT JOIN learning_entries e
                         ON e.topic_id = t.id AND e.user_id = %s
                       GROUP BY t.id, t.slug ORDER BY t.slug""",
                    (user_id,),
                ).fetchall()
                summary = knowledge["content"] if knowledge else None
                if summary:
                    summary = re.split(r"(?m)^## Текуща посока\s*$", summary)[0].strip()
                return StartContext(
                    instructions=policy["instructions"],
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
