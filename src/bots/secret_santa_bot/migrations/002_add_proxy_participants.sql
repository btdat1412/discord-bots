-- "Register dùm": let a Discord member enter someone who is not in the server.
--
-- A proxy participant is a normal row whose user_id is a synthetic id with a
-- "proxy:" prefix instead of a Discord snowflake, and whose registered_by
-- points at the member who entered them. That member receives the proxy's
-- assignment DM and passes it on.

ALTER TABLE santa_participants
    ADD COLUMN IF NOT EXISTS registered_by TEXT;

CREATE INDEX IF NOT EXISTS idx_santa_participants_registered_by
    ON santa_participants (game_id, registered_by);

-- Which Discord account actually received the DM. For a proxy this is the
-- registrar, not the participant, so the rollback knows whose messages to
-- delete.
ALTER TABLE santa_deliveries
    ADD COLUMN IF NOT EXISTS recipient_id TEXT;

UPDATE santa_deliveries SET recipient_id = user_id WHERE recipient_id IS NULL;
