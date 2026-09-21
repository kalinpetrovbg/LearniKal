import io
import os
import unittest
from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from learnika.api import app, get_s3_client


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType, IfNoneMatch):
        if (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed", "Message": "Exists"}}, "PutObject")
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def list_objects_v2(self, *, Bucket, Prefix, MaxKeys, ContinuationToken=None):
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + MaxKeys]
        result = {"Contents": [{"Key": key} for key in page]}
        if start + MaxKeys < len(keys):
            result["NextContinuationToken"] = str(start + MaxKeys)
        return result


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_env = {key: os.environ.get(key) for key in ("LEARNIKA_API_KEY", "LEARNIKA_S3_BUCKET")}
        os.environ.update({
            "LEARNIKA_API_KEY": "test-secret",
            "LEARNIKA_S3_BUCKET": "test-bucket",
        })
        self.s3 = FakeS3()
        self.s3.objects[("test-bucket", "learning/documents/learning_handoff.md")] = "Следващ въпрос: Kafka ordering".encode("utf-8")
        app.dependency_overrides[get_s3_client] = lambda: self.s3
        self.client = TestClient(app)
        self.headers = {"X-API-Key": "test-secret"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_documents_are_allowlisted_and_authenticated(self):
        self.assertEqual(self.client.get("/documents/handoff").status_code, 401)
        response = self.client.get("/documents/handoff", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Kafka ordering", response.json()["content"])
        self.assertEqual(self.client.get("/documents/unknown", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get("/documents/plan", headers=self.headers).status_code, 404)

    def test_create_read_list_and_idempotent_retry(self):
        entry_id = str(uuid4())
        payload = {
            "entry_id": entry_id,
            "technology": "KAFKA",
            "question": "How should events be partitioned?",
            "answer": "By order_id.",
            "evaluation": {"demonstrated_independently": "Per-order ordering"},
        }
        created = self.client.post("/entries", json=payload, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["technology"], "kafka")
        self.assertIn(("test-bucket", f"learning/entries/kafka/{entry_id}.json"), self.s3.objects)
        self.assertEqual(len(self.s3.objects), 2)

        repeated = self.client.post("/entries", json=payload, headers=self.headers)
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(repeated.json(), created.json())
        self.assertEqual(len(self.s3.objects), 2)

        fetched = self.client.get(f"/entries/kafka/{entry_id}", headers=self.headers)
        self.assertEqual(fetched.json(), created.json())
        listed = self.client.get("/entries?technology=kafka", headers=self.headers)
        self.assertEqual(listed.json()["items"], [created.json()])

        changed = self.client.post("/entries", json={**payload, "answer": "By customer_id."}, headers=self.headers)
        self.assertEqual(changed.status_code, 409)

    def test_invalid_input_and_missing_entry(self):
        self.assertEqual(self.client.post("/entries", json={"technology": "Kafka/other", "question": "Q", "answer": "A"}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/entries", json={"technology": "kafka", "question": "Q", "answer": "   "}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get(f"/entries/kafka/{uuid4()}", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
