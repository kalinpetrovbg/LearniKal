import hmac
import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from .models import (
    Answer, AnswerInput, AnswerPage, Document, Instruction, InstructionInput,
    InstructionUpdate, StartContext, Subtopic, SubtopicInput, SubtopicUpdate, Topic,
    TopicInput, TopicUpdate, User, UserInput, UserUpdate,
)
from .postgres import (
    DOCUMENTS, ConflictError, NotFoundError, PostgresStore, StorageError,
    SubtopicConflictError, TopicConflictError, TopicInUseError, UserConflictError,
)


app = FastAPI(title="LearniKal API", version="0.7.0")


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
    return JSONResponse(status_code=409, content={"detail": "Answer ID already exists with different content"})


@app.exception_handler(TopicConflictError)
async def topic_conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Topic slug or name already exists"})


@app.exception_handler(TopicInUseError)
async def topic_in_use_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Topic has answers; disable it instead"})


@app.exception_handler(SubtopicConflictError)
async def subtopic_conflict_handler(_request, _exc):
    return JSONResponse(status_code=409, content={"detail": "Subtopic slug or name already exists for this topic"})


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


@app.post("/answers", response_model=Answer, status_code=status.HTTP_201_CREATED,
          tags=["Answers"], dependencies=[Depends(require_api_key)])
def create_answer(payload: AnswerInput, store: PostgresStore = Depends(get_store)) -> Answer:
    return store.create_answer(payload)


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


@app.post("/subtopics", response_model=Subtopic, status_code=status.HTTP_201_CREATED,
          tags=["Topics"], dependencies=[Depends(require_api_key)])
def create_subtopic(payload: SubtopicInput, store: PostgresStore = Depends(get_store)) -> Subtopic:
    return store.create_subtopic(payload)


@app.get("/subtopics/list", response_model=list[Subtopic], tags=["Topics"],
         dependencies=[Depends(require_api_key)])
def list_subtopics(store: PostgresStore = Depends(get_store)) -> list[Subtopic]:
    return store.list_subtopics()


@app.patch("/subtopics/{subtopic_id}", response_model=Subtopic, tags=["Topics"],
           dependencies=[Depends(require_api_key)])
def update_subtopic(
    subtopic_id: Annotated[int, Path(ge=1)],
    payload: SubtopicUpdate,
    store: PostgresStore = Depends(get_store),
) -> Subtopic:
    return store.update_subtopic(subtopic_id, payload)


@app.delete("/subtopics/{subtopic_id}", status_code=status.HTTP_204_NO_CONTENT,
            tags=["Topics"], dependencies=[Depends(require_api_key)])
def delete_subtopic(
    subtopic_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> None:
    store.delete_subtopic(subtopic_id)


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


@app.post("/instructions", response_model=Instruction, status_code=status.HTTP_201_CREATED,
          tags=["Instructions"], dependencies=[Depends(require_api_key)])
def create_instruction(
    payload: InstructionInput,
    store: PostgresStore = Depends(get_store),
) -> Instruction:
    return store.create_instruction(payload)


@app.get("/instructions/list", response_model=list[Instruction], tags=["Instructions"],
         dependencies=[Depends(require_api_key)])
def list_instructions(store: PostgresStore = Depends(get_store)) -> list[Instruction]:
    return store.list_instructions()


@app.patch("/instructions/{instruction_id}", response_model=Instruction, tags=["Instructions"],
           dependencies=[Depends(require_api_key)])
def update_instruction(
    instruction_id: Annotated[int, Path(ge=1)],
    payload: InstructionUpdate,
    store: PostgresStore = Depends(get_store),
) -> Instruction:
    return store.update_instruction(instruction_id, payload)


@app.delete("/instructions/{instruction_id}", status_code=status.HTTP_204_NO_CONTENT,
            tags=["Instructions"], dependencies=[Depends(require_api_key)])
def delete_instruction(
    instruction_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> None:
    store.delete_instruction(instruction_id)


@app.get("/answers/list", response_model=AnswerPage, tags=["Answers"],
         dependencies=[Depends(require_api_key)])
def list_answers(
    topic_id: Annotated[int | None, Query(ge=1)] = None,
    subtopic_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[int, Query(ge=0)] = 0,
    store: PostgresStore = Depends(get_store),
) -> AnswerPage:
    return store.list_answers(topic_id, subtopic_id, limit, cursor)


@app.get("/answers/{answer_id}", response_model=Answer, tags=["Answers"],
         dependencies=[Depends(require_api_key)])
def get_answer(
    answer_id: Annotated[int, Path(ge=1)],
    store: PostgresStore = Depends(get_store),
) -> Answer:
    return store.get_answer(answer_id)
