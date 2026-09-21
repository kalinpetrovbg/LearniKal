# LearniKal API

FastAPI service for Team Lead learning sessions. PostgreSQL holds the learning
documents, historical sections, answers, and per-user state. Technologies share
one relational model and are treated equally.

## Current migration stage

The live EC2 deployment still uses S3. This checkout contains the PostgreSQL
cutover code; do not deploy it until the RDS database has been created and
imported. Follow [the RDS setup guide](deploy/postgres.md).

## API

- GET /health checks the PostgreSQL connection.
- GET /start returns study rules, imported knowledge, per-topic progress, a
  suggested technology, and an optional pending question.
- GET /documents and GET /documents/{name} read imported source documents from
  PostgreSQL.
- POST /entries saves an answer and evaluation. An entry_id can be reused for
  an idempotent retry. Optional difficulty is low, medium, or high; optional
  score is 0 through 5. Missing scores stay null.
- GET /entries?technology=kafka lists answers, with limit and numeric cursor.
- GET /entries/{technology}/{entry_id} reads one answer.

All routes except /health use the existing X-API-Key header. The key is read
from LEARNIKAL_API_KEY. The current single-user name is read from
LEARNIKAL_USERNAME (default: kalin); callers cannot choose another user.
LEARNIKAL_DATABASE_URL provides the PostgreSQL connection string.

## Local checks

Install requirements.txt in a virtual environment and run:

    python -m unittest discover -s tests

The unit tests use a fake store. A live PostgreSQL connection and S3 import
must be checked separately during cutover.
