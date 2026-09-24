# PostgreSQL on the existing EC2

The live API still reads S3. Complete this checklist before pushing the
PostgreSQL version to main, because pushes deploy automatically.

This setup runs PostgreSQL on the same Amazon Linux 2023 EC2 instance as Nginx
and FastAPI:

    EC2
    - Nginx
    - FastAPI
    - PostgreSQL

PostgreSQL listens locally on 127.0.0.1:5432. Do not open port 5432 to the
internet or add it to the public security group rules.

## Install PostgreSQL

Amazon Linux 2023 includes postgresql16 and postgresql16-server packages. On
the EC2 instance, install and initialize PostgreSQL:

    sudo dnf install postgresql16 postgresql16-server -y
    sudo postgresql-setup --initdb
    sudo systemctl enable --now postgresql
    sudo systemctl status postgresql --no-pager

The service should be active (running). If postgresql-setup is not available,
stop there and inspect the installed package scripts before continuing.

AWS package reference: [Amazon Linux 2023 PostgreSQL 16 packages](https://docs.aws.amazon.com/linux/al2023/release-notes/new-AL2-AL2023.12.html).

## Create the application database

Enter psql as the local PostgreSQL administrator:

    sudo -u postgres psql

Create the application user and database:

    CREATE USER learnikal WITH PASSWORD 'PUT_A_STRONG_PASSWORD_HERE';
    CREATE DATABASE learnikal OWNER learnikal;

Exit psql:

    \q

Check the local connection:

    psql -h 127.0.0.1 -U learnikal -d learnikal

If the prompt becomes learnikal=>, the database is ready.

## Configure EC2

Add the database URL to /etc/learnikal/learnikal.env. Keep the existing
LEARNIKAL_API_KEY exactly as it is.

    LEARNIKAL_DATABASE_URL=postgresql://learnikal:YOUR_PASSWORD@127.0.0.1:5432/learnikal
    LEARNIKAL_S3_BUCKET=learnikal-s3-bucket
    LEARNIKAL_USERNAME=kalin

Do not put the database password in GitHub or this repository. The S3 bucket
variable is needed only for the one-time import; the API does not read S3 after
cutover.

Prepare a separate checkout of the PostgreSQL branch on EC2. Keep the old
S3-backed service running from /opt/learnikal while importing. Do not push this
version to main yet; the GitHub workflow would restart the service before the
data is imported.

Install the new requirements in the existing virtual environment and run the
one-time import:

    /opt/learnikal/.venv/bin/python -m pip install -r /opt/learnikal-migration/requirements.txt
    sudo systemd-run --collect --unit=learnikal-import --wait -p User=ec2-user -p WorkingDirectory=/opt/learnikal-migration -p EnvironmentFile=/etc/learnikal/learnikal.env /opt/learnikal/.venv/bin/python /opt/learnikal-migration/migrate_s3.py
    sudo journalctl -u learnikal-import --no-pager

The import runs in a PostgreSQL transaction, checks the five document hashes,
historical-section count, and imported entry count. It does not delete S3
objects. Run it again after pausing new writes to the old API, then verify the
output.

Deploy the PostgreSQL API only after the import succeeds. Check
https://api.learnikal.com/health and authenticated /start, /documents/handoff,
and create/read/list answers. Remove S3 learning data and local Markdown copies
only after those checks.
*** Update File: NEXT_STEPS.md
@@
-1. Create a private PostgreSQL RDS database in eu-north-1 and connect it to
-   the existing EC2 instance. See deploy/postgres.md.
+1. Install PostgreSQL 16 on the existing EC2 instance. Keep it local on
+   127.0.0.1:5432 and do not open PostgreSQL to the internet. See
+   deploy/postgres.md.
@@
 5. Deploy the PostgreSQL API and check /health, /start, /documents, and the
    create/read/list flow. Only after these checks, remove the old S3 learning
    objects and the local Markdown copies.
*** Update File: README.md
@@
-The live EC2 deployment still uses S3. This checkout contains the PostgreSQL
-cutover code; do not deploy it until the RDS database has been created and
-imported. Follow [the RDS setup guide](deploy/postgres.md).
+The live EC2 deployment still uses S3. This checkout contains the PostgreSQL
+cutover code; do not deploy it until PostgreSQL has been installed locally on
+the EC2 instance and the S3 data has been imported. Follow
+[the PostgreSQL setup guide](deploy/postgres.md).
