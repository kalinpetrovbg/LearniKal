import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from learnikal.api import app, get_store
from learnikal.models import EntryPage, StartContext
from learnikal.postgres import ConflictError, NotFoundError


class FakeStore:
    def __init__(self):
        self.entries = {}

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
        old = self.entries.get(entry.entry_id)
        if old and old.model_dump(exclude={"created_at"}) != entry.model_dump(exclude={"created_at"}):
            raise ConflictError
        self.entries[entry.entry_id] = old or entry
        return self.entries[entry.entry_id]

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

    def test_documents_are_allowlisted(self):
        response = self.client.get("/documents/handoff", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Kafka ordering", response.json()["content"])
        self.assertEqual(self.client.get("/documents/unknown", headers=self.headers).status_code, 404)

    def test_create_read_list_and_idempotent_retry(self):
        entry_id = str(uuid4())
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

    def test_invalid_input_and_missing_entry(self):
        payload = {"technology": "kafka", "question": "Q", "answer": "A"}
        self.assertEqual(self.client.post("/entries", json={**payload, "score": 6}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/entries", json={**payload, "difficulty": "extreme"}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/entries", json={**payload, "answer": "  "}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get(f"/entries/kafka/{uuid4()}", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
