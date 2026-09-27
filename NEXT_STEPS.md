# LearniKal PostgreSQL Cutover

1. Install PostgreSQL 16 on the existing EC2 instance. Keep it local on
   127.0.0.1:5432 and do not open PostgreSQL to the internet. See
   deploy/postgres.md.
2. Put LEARNIKAL_DATABASE_URL in the existing root-owned
   /etc/learnikal/learnikal.env. Keep the existing LEARNIKAL_API_KEY.
3. Install updated Python dependencies on EC2. Run migrate_s3.py there while
   the old S3-backed API is still serving. The script imports all five
   documents and all S3 JSON entries, and verifies counts and document hashes.
4. Verify the imported rows directly in PostgreSQL. Pause old writes during
   the final import and run it again to catch late entries.
5. Deploy the PostgreSQL API and check /health, /start, typed instructions,
   and the create/read/list flow. Only after these checks, remove the old S3
   learning objects and local Markdown copies.

No database or S3 data has been modified by repository changes alone.
