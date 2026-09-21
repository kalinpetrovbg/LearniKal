BEGIN;

LOCK TABLE users, learning_entries, learning_state IN ACCESS EXCLUSIVE MODE;

ALTER TABLE users ADD COLUMN new_id integer;
WITH numbered_users AS (
    SELECT id AS old_id,
           row_number() OVER (ORDER BY username, id)::integer AS new_id
    FROM users
)
UPDATE users AS u
SET new_id = numbered_users.new_id
FROM numbered_users
WHERE u.id = numbered_users.old_id;

ALTER TABLE learning_entries ADD COLUMN new_user_id integer;
UPDATE learning_entries AS e
SET new_user_id = u.new_id
FROM users AS u
WHERE e.user_id = u.id;

ALTER TABLE learning_state ADD COLUMN new_user_id integer;
UPDATE learning_state AS s
SET new_user_id = u.new_id
FROM users AS u
WHERE s.user_id = u.id;

ALTER TABLE users ALTER COLUMN new_id SET NOT NULL;
ALTER TABLE learning_entries ALTER COLUMN new_user_id SET NOT NULL;
ALTER TABLE learning_state ALTER COLUMN new_user_id SET NOT NULL;

DROP INDEX learning_entries_user_topic_recent;
ALTER TABLE learning_entries DROP CONSTRAINT learning_entries_user_id_fkey;
ALTER TABLE learning_state DROP CONSTRAINT learning_state_user_id_fkey;
ALTER TABLE learning_state DROP CONSTRAINT learning_state_pkey;
ALTER TABLE users DROP CONSTRAINT users_pkey;

ALTER TABLE learning_entries DROP COLUMN user_id;
ALTER TABLE learning_entries RENAME COLUMN new_user_id TO user_id;
ALTER TABLE learning_state DROP COLUMN user_id;
ALTER TABLE learning_state RENAME COLUMN new_user_id TO user_id;
ALTER TABLE users DROP COLUMN id;
ALTER TABLE users RENAME COLUMN new_id TO id;

CREATE SEQUENCE users_id_seq;
ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq');
ALTER SEQUENCE users_id_seq OWNED BY users.id;
SELECT setval('users_id_seq', COALESCE((SELECT max(id) FROM users), 0) + 1, false);

ALTER TABLE users ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE learning_entries ADD CONSTRAINT learning_entries_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id);
ALTER TABLE learning_state ADD CONSTRAINT learning_state_pkey PRIMARY KEY (user_id);
ALTER TABLE learning_state ADD CONSTRAINT learning_state_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id);

CREATE INDEX learning_entries_user_topic_recent
    ON learning_entries (user_id, topic_id, created_at DESC, id DESC);

COMMIT;
