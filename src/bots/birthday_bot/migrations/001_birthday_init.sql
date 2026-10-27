-- Birthday bot: one birthday per user per server

CREATE TABLE IF NOT EXISTS birthdays (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_id BIGINT NOT NULL,
    day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 31),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    added_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (guild_id, discord_id)
);

CREATE INDEX IF NOT EXISTS idx_birthdays_month_day ON birthdays(month, day);
