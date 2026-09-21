# LearniKal Next Steps

This file tracks the next steps after the successful public HTTPS deployment and automated GitHub Actions deployment.

## Current state

- GitHub repository is `LearniKal`.
- Public API domain is `https://api.learnikal.com`.
- Swagger UI is available at `https://api.learnikal.com/docs#/`.
- EC2 service `learnikal.service` is active.
- Runtime paths are clean:
  - `/opt/learnikal`
  - `/etc/learnikal/learnikal.env`
- S3 bucket is `learnikal-s3-bucket`.
- `LEARNIKAL_API_KEY` is configured and intentionally kept as the project API key.
- GitHub Actions deploys every push to `main` over SSH to EC2.
- API has been verified locally and publicly:
  - `GET /health` returns `{"status":"ok"}`.
  - `GET /documents` works with `X-API-Key`.
  - `GET /documents/handoff` reads from S3.
  - `POST /entries` writes to S3.
  - `GET /entries/{technology}/{entry_id}` reads the saved entry.
  - `GET /entries?technology=kafka` lists saved entries.

## 1. Add a small entry-saving helper

Avoid manual `curl` for normal learning sessions. Add a small local helper script or CLI command that sends entries to the API with:

- technology
- question
- answer
- evaluation
- next_question

The helper should read configuration from environment variables or a local ignored config file, not from committed source code.

Done when:

- A learning entry can be saved without manually writing JSON.
- The helper returns the created `entry_id`.
- The saved entry can be read back from `/entries/{technology}/{entry_id}`.

## 2. Build a simple UI

After the API is stable, add a minimal web UI for daily use:

- list reference documents
- read a document
- create a learning entry
- list entries by technology
- open the latest or next question

Done when:

- The UI can perform the same read/write operations already proven through the API.
- The UI keeps API access simple and aligned with the current `LEARNIKAL_API_KEY` setup.

## 3. Improve learning workflow shape

Before adding a database, refine the saved entry format around the real study workflow:

- topic or technology
- question
- answer
- evaluation
- next question
- optional tags
- optional source document reference

Done when:

- Saved entries are consistent enough to support review sessions later.
- The API remains simple and easy to operate.

## 4. Consider PostgreSQL later

S3 is enough for the first working prototype and append-style records. PostgreSQL becomes useful when the project needs richer querying and learning analytics:

- search
- filters
- progress reports
- review scheduling
- statistics by topic
- stronger consistency constraints

Do not add PostgreSQL until the API and core learning workflow are proven useful.