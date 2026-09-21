# LearniKA API

LearniKA is a FastAPI service for recording learning questions and answers. This first stage stores individual records and the five existing Markdown reference documents in a private S3 bucket. PostgreSQL, a generated question bank, and a user interface are later stages.

## Structure

```text
learnika/                 API, validation, and S3 storage
tests/                    API tests with a fake S3 client
aws/iam-policy.json       scoped EC2 role permissions
deploy/                   Amazon Linux 2023 setup and systemd unit
main.py                   ASGI entry point
```

GitHub holds code and deployment configuration. S3 holds learning data only:

```text
s3://learnika-s3-bucket/learning/documents/<filename>.md
s3://learnika-s3-bucket/learning/entries/<technology>/<uuid>.json
```

The original documents under `releases/` remain untouched until migration is verified. See [the EC2 guide](deploy/amazon-linux-2023.md).

## Run locally

Use Python 3.11 or newer in a virtual environment, install `requirements.txt`, and set:

- `LEARNIKA_API_KEY`: a long random secret, sent by clients in `X-API-Key`.
- `LEARNIKA_S3_BUCKET`: `learnika-s3-bucket`.
- `AWS_DEFAULT_REGION`: `eu-north-1`.

AWS credentials follow the standard boto3 credential chain. Do not commit credentials or API keys. Start with `uvicorn main:app --host 127.0.0.1 --port 8000`; open `/docs` for interactive API documentation. All routes except `/health` require the API key. Run tests with `python -m unittest discover -s tests`.

## API

- `GET /documents` lists the five allowed document names.
- `GET /documents/{name}` reads `plan`, `knowledge`, `handoff`, `history`, or `patterns` from S3.
- `POST /entries` saves a question and answer. `technology`, `question`, and `answer` are required. `evaluation`, `next_question`, and `entry_id` are optional. Reuse an `entry_id` UUID for idempotent retries.
- `GET /entries?technology=kafka` lists saved records, with `limit` and `cursor` pagination.
- `GET /entries/{technology}/{entry_id}` reads one record.

Example request to `POST /entries`:

```json
{
  "technology": "KAFKA",
  "question": "How would you choose the message key for order events?",
  "answer": "Use order_id so events for one order go to one partition.",
  "evaluation": {
    "demonstrated_independently": "Preserved per-order ordering",
    "clarified_with_help": null,
    "remaining_unverified": "Hot partition risk"
  }
}
```

Keep Block Public Access on for the bucket. The initial API key is suitable for a single-user prototype; deploy HTTPS and stronger authentication before exposing the service to other laptops.
