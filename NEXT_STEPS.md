# LearniKal Next Steps

This file tracks the immediate next steps after the successful EC2 deployment and S3 write/read verification.

## Current state

- GitHub repository is `LearniKal`.
- EC2 service `learnikal.service` is active.
- Runtime paths are clean:
  - `/opt/learnikal`
  - `/etc/learnikal/learnikal.env`
- S3 bucket is `learnikal-s3-bucket`.
- API has been verified locally on EC2:
  - `GET /health` returns `{"status":"ok"}`.
  - `GET /documents` works with `X-API-Key`.
  - `GET /documents/handoff` reads from S3.
  - `POST /entries` writes to S3.
  - `GET /entries/{technology}/{entry_id}` reads the saved entry.
  - `GET /entries?technology=kafka` lists saved entries.

## 1. Replace the temporary API key

The current key is suitable only for testing. Before exposing the API publicly, replace it with a random secret.

On EC2:

```bash
openssl rand -hex 32
sudo nano /etc/learnikal/learnikal.env
sudo systemctl restart learnikal
curl -fsS http://127.0.0.1:8000/health
```

Update `LEARNIKAL_API_KEY` with the generated value. Do not commit the key to GitHub.

Done when:

- `/health` still works after restart.
- Protected routes only work with the new key.

## 2. Add public access through Nginx

Keep the FastAPI service bound to `127.0.0.1:8000`. Expose only Nginx on port `80` and proxy requests to the local API.

On EC2:

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx
sudo nano /etc/nginx/conf.d/learnikal.conf
```

Suggested config:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

In the EC2 Security Group, allow inbound HTTP TCP 80. Prefer restricting the source to the user's IP while testing.

Done when:

- `http://EC2_PUBLIC_IP/health` returns `{"status":"ok"}`.
- `http://EC2_PUBLIC_IP/documents` works with the API key.
- Port `8000` remains closed publicly.

## 3. Add a small entry-saving helper

Avoid manual `curl` for normal learning sessions. Add a small local helper script or CLI command that sends entries to the API with:

- technology
- question
- answer
- evaluation
- next_question

Done when:

- A learning entry can be saved without manually writing JSON.
- The helper returns the created `entry_id`.
- The saved entry can be read back from `/entries/{technology}/{entry_id}`.

## 4. Build a simple UI

After the API is stable, add a minimal web UI for daily use:

- list reference documents
- read a document
- create a learning entry
- list entries by technology
- open the latest or next question

Done when:

- The UI can perform the same read/write operations already proven through the API.
- API key handling is not exposed carelessly in public client code.

## 5. Consider PostgreSQL later

S3 is enough for the first working prototype and append-style records. PostgreSQL becomes useful when the project needs richer querying and learning analytics:

- search
- filters
- progress reports
- review scheduling
- statistics by topic
- stronger consistency constraints

Do not add PostgreSQL until the API and core learning workflow are proven useful.