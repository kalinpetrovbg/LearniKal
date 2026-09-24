import hmac
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from .models import (
    Document, Entry, EntryInput, EntryPage, StartContext, Topic, TopicInput, TopicUpdate,
    User, UserInput, UserUpdate,
)
from .postgres import (
    DOCUMENTS, ConflictError, NotFoundError, PostgresStore, StorageError,
    TopicConflictError, TopicInUseError, UserConflictError,
)


app = FastAPI(title="LearniKal API", version="0.5.5")


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("LEARNIKAL_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured")
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_store() -> PostgresStore:
    dsn = os.getenv("LEARNIKAL_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503, detail="PostgreSQL is not configured")
    return PostgresStore(dsn, os.getenv("LEARNIKAL_USERNAME", "kalin"))


@app.exception_handler(NotFoundError)
async def not_found_handler(_request, _exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(ConflictError)
async def conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Entry ID already exists with different content"})


@app.exception_handler(TopicConflictError)
async def topic_conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Topic slug or name already exists"})


@app.exception_handler(TopicInUseError)
async def topic_in_use_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Topic has learning entries; disable it instead"})


@app.exception_handler(UserConflictError)
async def user_conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Username or email already exists"})


@app.exception_handler(StorageError)
async def storage_error_handler(_request, _exc):
    return JSONResponse(status_code=503, content={"detail": "PostgreSQL is unavailable"})


@app.get("/health")
def health(store: PostgresStore = Depends(get_store)) -> dict[str, str]:
    store.ping()
    return {"status": "ok"}


@app.get("/start", response_model=StartContext, dependencies=[Depends(require_api_key)])
def start(store: PostgresStore = Depends(get_store)) -> StartContext:
    return store.start()


@app.get("/documents", dependencies=[Depends(require_api_key)])
def list_documents() -> list[str]:
    return list(DOCUMENTS)


@app.get("/documents/{name}", response_model=Document, dependencies=[Depends(require_api_key)])
def get_document(name: str, store: PostgresStore = Depends(get_store)) -> Document:
    if name not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="Document not found")
    return Document(name=name, content=store.get_document(name))


@app.post("/entries", response_model=Entry, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
def create_entry(payload: EntryInput, store: PostgresStore = Depends(get_store)) -> Entry:
    entry = Entry(
        **payload.model_dump(exclude={"entry_id"}),
        entry_id=payload.entry_id,
        created_at=datetime.now(timezone.utc),
    )
    return store.save_entry(entry)


@app.post("/topics", response_model=Topic, status_code=status.HTTP_201_CREATED, tags=["Topics"],
          dependencies=[Depends(require_api_key)])
def create_topic(payload: TopicInput, store: PostgresStore = Depends(get_store)) -> Topic:
    return store.create_topic(payload)


@app.get("/topics/list", response_model=list[Topic], tags=["Topics"],
         dependencies=[Depends(require_api_key)])
def list_topics(store: PostgresStore = Depends(get_store)) -> list[Topic]:
    return store.list_topics()


@app.patch("/topics/{topic_id}", response_model=Topic, tags=["Topics"],
           dependencies=[Depends(require_api_key)])
def update_topic(
    topic_id: Annotated[int, Path(ge=1)],
    payload: TopicUpdate,
    store: PostgresStore = Depends(get_store),
) -> Topic:
    return store.update_topic(topic_id, payload)


@app.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Topics"],
            dependencies=[Depends(require_api_key)])
def delete_topic(
    topic_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> None:
    store.delete_topic(topic_id)


@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"],
          dependencies=[Depends(require_api_key)])
def create_user(payload: UserInput, store: PostgresStore = Depends(get_store)) -> User:
    return store.create_user(payload)


@app.get("/users/list", response_model=list[User], tags=["Users"],
         dependencies=[Depends(require_api_key)])
def list_users(store: PostgresStore = Depends(get_store)) -> list[User]:
    return store.list_users()


@app.patch("/users/{user_id}", response_model=User, tags=["Users"], dependencies=[Depends(require_api_key)])
def update_user(
    user_id: Annotated[int, Path(ge=1)],
    payload: UserUpdate,
    store: PostgresStore = Depends(get_store),
) -> User:
    return store.update_user(user_id, payload)


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"],
            dependencies=[Depends(require_api_key)])
def delete_user(
    user_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> None:
    store.delete_user(user_id)


@app.get("/entries/{technology}/{entry_id}", response_model=Entry, dependencies=[Depends(require_api_key)])
def get_entry(
    technology: Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")],
    entry_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> Entry:
    return store.get_entry(technology.lower(), entry_id)


@app.get("/entries", response_model=EntryPage, dependencies=[Depends(require_api_key)])
def list_entries(
    technology: Annotated[str, Query(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[int, Query(ge=0)] = 0,
    store: PostgresStore = Depends(get_store),
) -> EntryPage:
    return store.list_entries(technology.lower(), limit, cursor)
