BEGIN;

LOCK TABLE learning_entries IN ACCESS EXCLUSIVE MODE;

DROP INDEX IF EXISTS learning_entries_user_topic_recent;
ALTER TABLE learning_entries DROP CONSTRAINT learning_entries_pkey;
ALTER TABLE learning_entries RENAME COLUMN id TO old_uuid_id;
ALTER TABLE learning_entries ADD COLUMN id integer;

WITH ordered_entries AS (
    SELECT old_uuid_id,
           row_number() OVER (ORDER BY created_at, old_uuid_id)::integer AS new_id
    FROM learning_entries
)
UPDATE learning_entries AS entry
SET id = ordered_entries.new_id
FROM ordered_entries
WHERE entry.old_uuid_id = ordered_entries.old_uuid_id;

CREATE SEQUENCE learning_entries_id_seq;
ALTER TABLE learning_entries ALTER COLUMN id SET NOT NULL;
ALTER TABLE learning_entries ALTER COLUMN id SET DEFAULT nextval('learning_entries_id_seq');
ALTER SEQUENCE learning_entries_id_seq OWNED BY learning_entries.id;
SELECT setval(
    'learning_entries_id_seq',
    COALESCE((SELECT max(id) FROM learning_entries), 0) + 1,
    false
);

ALTER TABLE learning_entries ADD CONSTRAINT learning_entries_pkey PRIMARY KEY (id);
ALTER TABLE learning_entries DROP COLUMN old_uuid_id;

CREATE INDEX learning_entries_user_topic_recent
    ON learning_entries (user_id, topic_id, created_at DESC, id DESC);

COMMIT;
