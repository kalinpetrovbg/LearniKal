import hmac
import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import BotoCoreError
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from .models import Document, Entry, EntryInput, EntryPage
from .storage import DOCUMENTS, ConflictError, NotFoundError, S3Store, StorageError


app = FastAPI(title="LearniKA API", version="0.2.0")


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("LEARNIKA_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_s3_client():
    try:
        return boto3.client("s3")
    except BotoCoreError as exc:
        raise HTTPException(status_code=503, detail="S3 client is not configured") from exc


def get_store(client=Depends(get_s3_client)) -> S3Store:
    bucket = os.getenv("LEARNIKA_S3_BUCKET")
    if not bucket:
        raise HTTPException(status_code=503, detail="S3 bucket is not configured")
    return S3Store(client, bucket)


@app.exception_handler(NotFoundError)
async def not_found_handler(_request, _exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(ConflictError)
async def conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Entry ID already exists with different content"})


@app.exception_handler(StorageError)
async def storage_error_handler(_request, _exc):
    return JSONResponse(status_code=502, content={"detail": "S3 operation failed"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/documents", dependencies=[Depends(require_api_key)])
def list_documents() -> list[str]:
    return list(DOCUMENTS)


@app.get("/documents/{name}", response_model=Document, dependencies=[Depends(require_api_key)])
def get_document(name: str, store: S3Store = Depends(get_store)) -> Document:
    if name not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="Document not found")
    return Document(name=name, content=store.get_document(name))


@app.post("/entries", response_model=Entry, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
def create_entry(payload: EntryInput, store: S3Store = Depends(get_store)) -> Entry:
    entry = Entry(
        **payload.model_dump(exclude={"entry_id"}),
        entry_id=payload.entry_id or uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    return store.save_entry(entry)


@app.get("/entries/{technology}/{entry_id}", response_model=Entry, dependencies=[Depends(require_api_key)])
def get_entry(
    technology: Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")],
    entry_id: UUID,
    store: S3Store = Depends(get_store),
) -> Entry:
    return store.get_entry(technology.lower(), entry_id)


@app.get("/entries", response_model=EntryPage, dependencies=[Depends(require_api_key)])
def list_entries(
    technology: Annotated[str, Query(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    store: S3Store = Depends(get_store),
) -> EntryPage:
    return store.list_entries(technology.lower(), limit, cursor)
