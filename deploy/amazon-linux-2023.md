# LearniKal on Amazon Linux 2023

The API runs on EC2; GitHub stores code and the private S3 bucket stores data. The service binds to `127.0.0.1:8000`. Do not open port 8000 to the internet; add an HTTPS reverse proxy and authentication before access from other laptops.

## IAM

Attach `LearniKal-EC2-Role` to the instance. It needs `AmazonSSMManagedInstanceCore` and the inline S3 permissions in `aws/iam-policy.json`. Update the existing inline policy to match that file before migration. Keep S3 Block Public Access enabled.

## S3 layout

Use the private `learnikal-s3-bucket` bucket with the existing `learning/documents/` objects. The service stores new answer records under `learning/entries/`.

## Install

Run on the EC2 instance after the GitHub repository has been populated. The HTTPS clone command works for a public repository; for a private repository, configure a read-only GitHub deploy key on the instance without putting its private key in S3 or this repository.

```bash
sudo dnf install -y git python3.11 python3.11-pip
sudo mkdir -p /opt/learnikal /etc/learnikal
sudo chown ec2-user:ec2-user /opt/learnikal
git clone https://github.com/kalinpetrovbg/LearniKal.git /opt/learnikal
cd /opt/learnikal
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Do not change the system `/usr/bin/python3`.

Generate a secret on EC2 with `openssl rand -hex 32`. Create `/etc/learnikal/learnikal.env` owned by root with mode `600`, replacing the placeholder with the generated value:

```bash
sudo install -o root -g root -m 600 /dev/null /etc/learnikal/learnikal.env
sudo nano /etc/learnikal/learnikal.env
```

```ini
LEARNIKAL_API_KEY=REPLACE_WITH_RANDOM_SECRET
LEARNIKAL_S3_BUCKET=learnikal-s3-bucket
AWS_DEFAULT_REGION=eu-north-1
```

Install and check the service:

```bash
sudo cp /opt/learnikal/deploy/learnikal.service /etc/systemd/system/learnikal.service
sudo systemctl daemon-reload
sudo systemctl enable --now learnikal
sudo systemctl status learnikal --no-pager
curl -fsS http://127.0.0.1:8000/health
```

After a future code update, run `git pull --ff-only` from `/opt/learnikal`, install changed requirements, and restart `learnikal`. The S3 data remains separate from the checkout.
