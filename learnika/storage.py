from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

from .models import Entry, EntryPage


DOCUMENTS = {
    "plan": "TEAM_LEAD_LEARNING_PLAN.md",
    "knowledge": "LEARNING_KNOWLEDGE_SUMMARY.md",
    "handoff": "learning_handoff.md",
    "history": "LEARNING_HISTORY.md",
    "patterns": "design_patterns.md",
}
DOCUMENT_PREFIX = "learning/documents"
ENTRY_PREFIX = "learning/entries"


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class StorageError(Exception):
    pass


def document_key(name: str) -> str:
    return f"{DOCUMENT_PREFIX}/{DOCUMENTS[name]}"


def entry_key(technology: str, entry_id: UUID) -> str:
    return f"{ENTRY_PREFIX}/{technology}/{entry_id}.json"


class S3Store:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    def _read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                raise NotFoundError from exc
            raise StorageError("S3 read failed") from exc
        except BotoCoreError as exc:
            raise StorageError("S3 read failed") from exc

    def get_document(self, name: str) -> str:
        try:
            return self._read(document_key(name)).decode("utf-8")
        except UnicodeError as exc:
            raise StorageError("Document is not valid UTF-8") from exc

    def get_entry(self, technology: str, entry_id: UUID) -> Entry:
        return self._get_entry_by_key(entry_key(technology, entry_id))

    def _get_entry_by_key(self, key: str) -> Entry:
        try:
            return Entry.model_validate_json(self._read(key))
        except ValueError as exc:
            raise StorageError("Stored entry is invalid") from exc

    def save_entry(self, entry: Entry) -> Entry:
        key = entry_key(entry.technology, entry.entry_id)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=entry.model_dump_json().encode("utf-8"),
                ContentType="application/json; charset=utf-8",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "PreconditionFailed":
                existing = self.get_entry(entry.technology, entry.entry_id)
                if existing.model_dump(exclude={"created_at"}) == entry.model_dump(exclude={"created_at"}):
                    return existing
                raise ConflictError from exc
            raise StorageError("S3 write failed") from exc
        except BotoCoreError as exc:
            raise StorageError("S3 write failed") from exc
        return entry

    def list_entries(self, technology: str, limit: int, cursor: str | None) -> EntryPage:
        arguments = {
            "Bucket": self.bucket,
            "Prefix": f"{ENTRY_PREFIX}/{technology}/",
            "MaxKeys": limit,
        }
        if cursor:
            arguments["ContinuationToken"] = cursor
        try:
            response = self.client.list_objects_v2(**arguments)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError("S3 list failed") from exc
        items = [self._get_entry_by_key(item["Key"]) for item in response.get("Contents", [])]
        return EntryPage(items=items, next_cursor=response.get("NextContinuationToken"))
