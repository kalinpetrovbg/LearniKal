# LearniKal API

LearniKal is a FastAPI service for Python and Data Engineering Team Lead learning sessions. It stores users, learning topics and subtopics, typed instructions, scored answers, and progress in PostgreSQL.

The production service runs on AWS EC2. Nginx terminates HTTPS and proxies the API to Uvicorn on `127.0.0.1:8000`; PostgreSQL runs locally on the same EC2 instance. A push to the `main` branch deploys the current code automatically through GitHub Actions.

## API documentation

FastAPI provides interactive API documentation at:

- `/docs` — Swagger UI
- `/redoc` — ReDoc
- `/openapi.json` — OpenAPI schema

## Authentication and configuration

Every endpoint except `GET /health` requires an `X-API-Key` request header.

The service reads these environment variables:

- `LEARNIKAL_API_KEY` — shared API key required by protected routes.
- `LEARNIKAL_DATABASE_URL` — PostgreSQL connection string.
- `LEARNIKAL_USERNAME` — default learning user used by `/start` and answer reads; defaults to `kalin`.

Production values are stored in `/etc/learnikal/learnikal.env` on EC2 and must not be committed to the repository.

## Endpoints

### Health and learning context

- `GET /health` checks the PostgreSQL connection.
- `GET /start` returns active `behavior` instructions, the `knowledge` summary, and per-topic progress. It does not choose the next question; future question selection will use separate logic.

### Answers

- `POST /answers` records an evaluated answer.
- `GET /answers/list` lists answers for the configured learning user. Results can be filtered by `topic_id` and `subtopic_id` and paginated with `limit` and `cursor`.
- `GET /answers/{answer_id}` returns one answer belonging to the configured learning user.

An answer records its topic and optional subtopic and question, plus score, difficulty, independence, clarity, completeness, and confidence values. Supplying an existing answer `id` with identical data is treated as an idempotent retry; different data returns `409 Conflict`.

### Topics and subtopics

- `POST /topics`
- `GET /topics/list`
- `PATCH /topics/{topic_id}`
- `DELETE /topics/{topic_id}`
- `POST /subtopics`
- `GET /subtopics/list`
- `PATCH /subtopics/{subtopic_id}`
- `DELETE /subtopics/{subtopic_id}`

Topic and subtopic slugs are normalized to lowercase. Topics that already have answers cannot be deleted and should be disabled with `is_active: false` instead.

The curated [subtopic catalog](docs/subtopics-catalog.md) contains 715 entries: 55 for each of the 13 topics, including the 21 existing subtopics. The canonical [CSV](docs/subtopics-catalog.csv) can be validated without a database:

```sh
python deploy/import-subtopics-catalog.py --validate
```

The importer previews changes by default and inserts missing entries only with `--apply`. It preserves existing IDs, names and active flags and stops on conflicting mappings. This catalog import is manual and is not part of the deployment workflow. See the catalog guide for EC2 commands.

The proposed flow from `/start` through random question selection, generation and evaluation is documented in [Learning flow proposal](docs/learning-flow-proposal.md). It describes future behavior; the new question-selection and evaluation endpoints are not implemented yet.

### Questions

- `POST /questions`
- `GET /questions/list`
- `PATCH /questions/{question_id}`
- `DELETE /questions/{question_id}`

Each question belongs to a topic and one of that topic's subtopics, has a difficulty from 1 to 5, and can be enabled or disabled with `is_active`. The list endpoint can filter by `topic_id`, `subtopic_id`, and `is_active`. Question text must be unique within a subtopic, ignoring letter case.

Answers can reference a question with `question_id`. When the question is valid and `subtopic_id` is omitted from the answer, the API takes the subtopic from the question. Deleting a question keeps its historical answers and clears their `question_id` reference.

### Users

- `POST /users`
- `GET /users/list`
- `PATCH /users/{user_id}`
- `DELETE /users/{user_id}`

Passwords are hashed with Argon2id and are never returned by the API. The current API uses the shared API key and does not expose a user login endpoint.

### Study instructions

- `POST /instructions`
- `GET /instructions/list` (filter by type, for example `?type=knowledge` or `?type=history`)
- `PATCH /instructions/{instruction_id}`
- `DELETE /instructions/{instruction_id}`

Only active `behavior` instructions are included in `/start`, ordered by position and ID. Other instruction types hold the learning plan, knowledge summary, handoff, history, and design-pattern notes.

## Local development

Create and activate a virtual environment, then install the development requirements:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Set the required environment variables and start the API:

```powershell
$env:LEARNIKAL_DATABASE_URL = "postgresql://USER:PASSWORD@127.0.0.1:5432/learnikal"
$env:LEARNIKAL_API_KEY = "your-local-api-key"
$env:LEARNIKAL_USERNAME = "kalin"
uvicorn main:app --reload
```

The local API is available at `http://127.0.0.1:8000`, with Swagger UI at `http://127.0.0.1:8000/docs`.

Run the unit tests with:

```powershell
python -m unittest discover -s tests
```

The API tests use an in-memory fake store. PostgreSQL connectivity and production migrations require separate integration checks.

## Database

[`schema.sql`](schema.sql) describes the complete PostgreSQL schema. The `deploy/migrate-*.py` scripts upgrade existing production tables and data during deployment. The historical S3 import utility remains in the repository for migration purposes; PostgreSQL is the active application database.

`deploy/import-legacy-questions.py` is a one-time, repeatable recovery tool for legacy S3 entries. It matches each entry to an existing answer by user, topic, and creation timestamp, then creates an inactive legacy subtopic and question and links the answer. It performs a read-only dry run unless called with `--apply`.

## Deployment

The workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) runs on every push to `main` and can also be started manually. It connects to EC2 over SSH and:

1. Fast-forwards `/opt/learnikal` to the latest `main` commit.
2. Installs the current Python requirements.
3. Runs the topic, subtopic, instruction, answer, and question migrations.
4. Restarts the `learnikal` systemd service.
5. Checks `http://127.0.0.1:8000/health` and prints recent service logs if the check fails.

Because `main` deploys automatically, changes should be tested before they are pushed or merged into that branch.
