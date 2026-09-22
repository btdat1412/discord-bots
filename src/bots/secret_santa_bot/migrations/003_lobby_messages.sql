-- A game can be shown by more than one message: the original one posted by
-- /secret-santa, plus any copy pushed to the bottom of a busy channel by
-- /my-current-game or the daily bump job.
--
-- Every copy carries the same buttons, so every copy has to stay in sync and
-- keep working. This table is the list of messages to refresh; santa_games
-- .message_id stays as the original for reference.

CREATE TABLE IF NOT EXISTS santa_lobby_messages (
    id          SERIAL PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES santa_games (id) ON DELETE CASCADE,
    channel_id  TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_santa_lobby_messages
    ON santa_lobby_messages (game_id, message_id);
CREATE INDEX IF NOT EXISTS idx_santa_lobby_messages_game
    ON santa_lobby_messages (game_id);

-- Adopt the message every existing game already has.
INSERT INTO santa_lobby_messages (game_id, channel_id, message_id, is_primary)
SELECT id, channel_id, message_id, TRUE
FROM santa_games
ON CONFLICT DO NOTHING;
