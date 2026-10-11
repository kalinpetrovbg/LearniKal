# PostgreSQL on the existing EC2

The live API uses PostgreSQL. Pushes to `main` deploy automatically.

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
    LEARNIKAL_USERNAME=kalin

Do not put the database password in GitHub or this repository. The deployment
workflow installs dependencies, runs database migrations, and restarts the API.
