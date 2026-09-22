-- Secret Santa: games, participants, and the DM delivery log.
--
-- Answers live in a JSONB column keyed by the edition's field keys, so a new
-- year only needs a new edition file — never a migration.

CREATE TABLE IF NOT EXISTS santa_games (
    id            SERIAL PRIMARY KEY,
    edition_key   TEXT NOT NULL,
    guild_id      TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    message_id    TEXT NOT NULL,
    host_id       TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN | COMPLETED | CANCELLED
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_santa_games_guild ON santa_games (guild_id);
CREATE INDEX IF NOT EXISTS idx_santa_games_state ON santa_games (state);
CREATE INDEX IF NOT EXISTS idx_santa_games_edition ON santa_games (edition_key);

CREATE TABLE IF NOT EXISTS santa_participants (
    id                  SERIAL PRIMARY KEY,
    game_id             INTEGER NOT NULL REFERENCES santa_games (id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL,
    display_name        TEXT,
    display_name_server TEXT,
    avatar_url          TEXT,
    answers             JSONB NOT NULL DEFAULT '{}'::jsonb,
    public_opt_in       BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_to         TEXT,
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_santa_participants_game_user
    ON santa_participants (game_id, user_id);
CREATE INDEX IF NOT EXISTS idx_santa_participants_user
    ON santa_participants (user_id);

-- Every assignment DM the bot sends is logged here so a failed start can be
-- rolled back: the bot deletes the messages it already delivered.
CREATE TABLE IF NOT EXISTS santa_deliveries (
    id              SERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES santa_games (id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    dm_channel_id   TEXT NOT NULL,
    dm_message_id   TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_santa_deliveries_game
    ON santa_deliveries (game_id);
