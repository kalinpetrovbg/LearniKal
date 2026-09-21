# LearniKA on Amazon Linux 2023

The API runs on EC2; GitHub stores code and the private S3 bucket stores data. The service binds to `127.0.0.1:8000`. Do not open port 8000 to the internet; add an HTTPS reverse proxy and authentication before access from other laptops.

## IAM

Attach `LearniKA-EC2-Role` to the instance. It needs `AmazonSSMManagedInstanceCore` and the inline S3 permissions in `aws/iam-policy.json`. Update the existing inline policy to match that file before migration. Keep S3 Block Public Access enabled.

## Migrate documents

Run these in the EC2 browser terminal. The source `releases/` objects stay in place until you verify all five copies.

```bash
set -e
bucket=learnika-s3-bucket
for name in TEAM_LEAD_LEARNING_PLAN.md LEARNING_KNOWLEDGE_SUMMARY.md learning_handoff.md LEARNING_HISTORY.md design_patterns.md; do
  aws s3 cp "s3://$bucket/releases/$name" "s3://$bucket/learning/documents/$name" --region eu-north-1
  aws s3api head-object --bucket "$bucket" --key "learning/documents/$name" --region eu-north-1 --query 'ContentLength' --output text
done
```

Inspect the content through the API after deployment. Remove old `releases/` objects only after checking the copies and deciding they are no longer needed. Then remove the legacy `releases/*` permission from the role.

## Install

Run on the EC2 instance after the GitHub repository has been populated. The HTTPS clone command works for a public repository; for a private repository, configure a read-only GitHub deploy key on the instance without putting its private key in S3 or this repository.

```bash
sudo dnf install -y git python3.11 python3.11-pip
sudo mkdir -p /opt/learnika /etc/learnika
sudo chown ec2-user:ec2-user /opt/learnika
git clone https://github.com/kalinpetrovbg/LearniKA.git /opt/learnika
cd /opt/learnika
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Do not change the system `/usr/bin/python3`.

Generate a secret on EC2 with `openssl rand -hex 32`. Create `/etc/learnika/learnika.env` owned by root with mode `600`, replacing the placeholder with the generated value:

```bash
sudo install -o root -g root -m 600 /dev/null /etc/learnika/learnika.env
sudo nano /etc/learnika/learnika.env
```

```ini
LEARNIKA_API_KEY=REPLACE_WITH_RANDOM_SECRET
LEARNIKA_S3_BUCKET=learnika-s3-bucket
AWS_DEFAULT_REGION=eu-north-1
```

Install and check the service:

```bash
sudo cp /opt/learnika/deploy/learnika.service /etc/systemd/system/learnika.service
sudo systemctl daemon-reload
sudo systemctl enable --now learnika
sudo systemctl status learnika --no-pager
curl -fsS http://127.0.0.1:8000/health
```

After a future code update, run `git pull --ff-only` from `/opt/learnika`, install changed requirements, and restart `learnika`. The S3 data remains separate from the checkout.
