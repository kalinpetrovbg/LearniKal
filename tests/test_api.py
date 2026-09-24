import os
import unittest

from fastapi.testclient import TestClient

from learnikal.api import app, get_store, require_api_key
from learnikal.models import EntryPage, StartContext, Topic, User
from learnikal.postgres import ConflictError, NotFoundError, TopicConflictError, UserConflictError


class FakeStore:
    def __init__(self):
        self.entries = {}
        self.topics = {}
        self.users = {}

    def start(self):
        return StartContext(
            instructions="Всички технологии са равнопоставени.",
            knowledge_summary="Kafka е начална тема.",
            suggested_technology="kafka",
            next_question="Как избираш message key?",
        )

    def ping(self):
        return None

    def get_document(self, name):
        if name != "handoff":
            raise NotFoundError
        return "Следващ въпрос: Kafka ordering"

    def save_entry(self, entry):
        if not entry.entry_id:
            entry = entry.model_copy(update={"entry_id": len(self.entries) + 1})
        old = self.entries.get(entry.entry_id)
        if old and old.model_dump(exclude={"created_at"}) != entry.model_dump(exclude={"created_at"}):
            raise ConflictError
        self.entries[entry.entry_id] = old or entry
        return self.entries[entry.entry_id]

    def create_topic(self, topic):
        if any(item.slug == topic.slug or item.name.lower() == topic.name.lower()
               for item in self.topics.values()):
            raise TopicConflictError
        topic_id = len(self.topics) + 1
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        created = Topic(id=topic_id, **topic.model_dump(), created_at=now, updated_at=now)
        self.topics[topic_id] = created
        return created

    def update_topic(self, topic_id, topic):
        old = self.topics.get(topic_id)
        if old is None:
            raise NotFoundError
        slug = topic.slug if topic.slug is not None else old.slug
        name = topic.name if topic.name is not None else old.name
        if any(
            item.id != topic_id and (item.slug == slug or item.name.lower() == name.lower())
            for item in self.topics.values()
        ):
            raise TopicConflictError
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        updated = old.model_copy(update={
            "slug": slug,
            "name": name,
            "is_active": topic.is_active if topic.is_active is not None else old.is_active,
            "updated_at": now,
        })
        self.topics[topic_id] = updated
        return updated

    def create_user(self, user):
        if any(item.username == user.username or item.email == user.email for item in self.users.values()):
            raise UserConflictError
        user_id = len(self.users) + 1
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        created = User(
            id=user_id, username=user.username, first_name=user.first_name,
            last_name=user.last_name, email=user.email, created_at=now, updated_at=now,
        )
        self.users[user_id] = created
        return created

    def update_user(self, user_id, user):
        old = self.users.get(user_id)
        if old is None:
            raise NotFoundError
        username = user.username if user.username is not None else old.username
        email = user.email if user.email is not None else old.email
        if any(
            item.id != user_id and (item.username == username or item.email == email)
            for item in self.users.values()
        ):
            raise UserConflictError
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        updated = old.model_copy(update={
            "username": username,
            "first_name": user.first_name if user.first_name is not None else old.first_name,
            "last_name": user.last_name if user.last_name is not None else old.last_name,
            "email": email,
            "updated_at": now,
        })
        self.users[user_id] = updated
        return updated

    def get_entry(self, technology, entry_id):
        entry = self.entries.get(entry_id)
        if entry is None or entry.technology != technology:
            raise NotFoundError
        return entry

    def list_entries(self, technology, limit, cursor):
        items = [entry for entry in self.entries.values() if entry.technology == technology]
        page = items[cursor:cursor + limit]
        return EntryPage(items=page, next_cursor=str(cursor + limit) if len(items) > cursor + limit else None)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_key = os.environ.get("LEARNIKAL_API_KEY")
        os.environ["LEARNIKAL_API_KEY"] = "test-key"
        self.store = FakeStore()
        app.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(app)
        self.headers = {"X-API-Key": "test-key"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        if self.previous_key is None:
            os.environ.pop("LEARNIKAL_API_KEY", None)
        else:
            os.environ["LEARNIKAL_API_KEY"] = self.previous_key

    def test_start_requires_key_and_returns_context(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/start").status_code, 401)
        response = self.client.get("/start", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggested_technology"], "kafka")
        self.assertIn("равнопоставени", response.json()["instructions"])

    def test_non_ascii_wrong_key_is_unauthorized(self):
        with self.assertRaises(Exception) as caught:
            require_api_key("грешен")
        self.assertEqual(caught.exception.status_code, 401)

    def test_documents_are_allowlisted(self):
        response = self.client.get("/documents/handoff", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Kafka ordering", response.json()["content"])
        self.assertEqual(self.client.get("/documents/unknown", headers=self.headers).status_code, 404)

    def test_create_read_list_and_idempotent_retry(self):
        entry_id = 123
        payload = {
            "entry_id": entry_id, "technology": "KAFKA",
            "question": "How should events be partitioned?", "answer": "By order_id.",
            "evaluation": {"demonstrated_independently": "Per-order ordering"},
            "difficulty": "high", "score": 4,
        }
        created = self.client.post("/entries", json=payload, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["technology"], "kafka")
        self.assertEqual(self.client.post("/entries", json=payload, headers=self.headers).json(), created.json())
        self.assertEqual(
            self.client.get(f"/entries/kafka/{entry_id}", headers=self.headers).json(), created.json()
        )
        self.assertEqual(
            self.client.get("/entries?technology=kafka", headers=self.headers).json()["items"],
            [created.json()],
        )
        changed = self.client.post(
            "/entries", json={**payload, "answer": "By customer_id."}, headers=self.headers
        )
        self.assertEqual(changed.status_code, 409)

    def test_generated_entry_id_is_integer(self):
        payload = {
            "technology": "postgresql",
            "question": "Q",
            "answer": "A",
        }
        created = self.client.post("/entries", json=payload, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["entry_id"], 1)

    def test_create_and_update_topic(self):
        created = self.client.post(
            "/topics", json={"slug": "MONGODB", "name": "MongoDB"}, headers=self.headers
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["slug"], "mongodb")
        self.assertTrue(created.json()["is_active"])
        duplicate = self.client.post(
            "/topics", json={"slug": "mongodb", "name": "Mongo DB"}, headers=self.headers
        )
        self.assertEqual(duplicate.status_code, 409)
        disabled = self.client.patch("/topics/1", json={"is_active": False}, headers=self.headers)
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["is_active"])
        self.assertEqual(self.client.patch("/topics/999", json={"is_active": False}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.patch("/topics/1/disable", headers=self.headers).status_code, 404)

    def test_create_inactive_topic(self):
        created = self.client.post(
            "/topics", json={"slug": "queues", "name": "Queues", "is_active": False},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["slug"], "queues")
        self.assertFalse(created.json()["is_active"])

    def test_update_topic_can_enable_disable_and_rename(self):
        created = self.client.post(
            "/topics", json={"slug": "queues", "name": "Queues", "is_active": False},
            headers=self.headers,
        ).json()

        updated = self.client.patch(
            f"/topics/{created['id']}",
            json={"slug": "MESSAGING", "name": "Messaging", "is_active": True},
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["slug"], "messaging")
        self.assertEqual(updated.json()["name"], "Messaging")
        self.assertTrue(updated.json()["is_active"])
        self.assertNotIn("created_at", updated.request.content.decode("utf-8"))
        self.assertNotIn("updated_at", updated.request.content.decode("utf-8"))

        self.client.post("/topics", json={"slug": "kafka", "name": "Kafka"}, headers=self.headers)
        duplicate = self.client.patch(
            f"/topics/{created['id']}", json={"slug": "kafka"}, headers=self.headers
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.patch("/topics/999", json={"is_active": True}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.patch(f"/topics/{created['id']}", json={}, headers=self.headers).status_code, 422)

    def test_create_user(self):
        payload = {
            "username": "MARTIN", "first_name": "Martin", "last_name": "Ivanov",
            "email": "MARTIN@example.com", "password": "secret",
        }
        created = self.client.post("/users", json=payload, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["username"], "martin")
        self.assertEqual(created.json()["email"], "martin@example.com")
        self.assertNotIn("password", created.json())
        self.assertNotIn("password_hash", created.json())

        duplicate = self.client.post("/users", json=payload, headers=self.headers)
        self.assertEqual(duplicate.status_code, 409)

    def test_update_user(self):
        created = self.client.post("/users", json={
            "username": "MARTIN", "first_name": "Martin", "last_name": "Ivanov",
            "email": "MARTIN@example.com", "password": "secret",
        }, headers=self.headers).json()

        updated = self.client.patch(
            f"/users/{created['id']}",
            json={"first_name": "Maria", "email": "MARIA@example.com", "password": "new-secret"},
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["username"], "martin")
        self.assertEqual(updated.json()["first_name"], "Maria")
        self.assertEqual(updated.json()["email"], "maria@example.com")
        self.assertNotIn("password", updated.json())
        self.assertNotIn("password_hash", updated.json())

        self.client.post("/users", json={
            "username": "ivan", "first_name": "Ivan", "last_name": "Petrov",
            "email": "ivan@example.com", "password": "secret",
        }, headers=self.headers)
        duplicate = self.client.patch(
            f"/users/{created['id']}", json={"email": "ivan@example.com"}, headers=self.headers
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.patch("/users/999", json={"first_name": "Nobody"}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.patch(f"/users/{created['id']}", json={}, headers=self.headers).status_code, 422)

    def test_invalid_input_and_missing_entry(self):
        payload = {"technology": "kafka", "question": "Q", "answer": "A"}
        self.assertEqual(self.client.post("/entries", json={**payload, "score": 6}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/entries", json={**payload, "difficulty": "extreme"}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/entries", json={**payload, "answer": "  "}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get("/entries/kafka/999", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
