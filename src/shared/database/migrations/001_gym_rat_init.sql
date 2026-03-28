-- Gym Rat: users and check-ins

CREATE TABLE IF NOT EXISTS gym_users (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT UNIQUE NOT NULL,
    discord_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gym_checkins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES gym_users(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL,
    checked_in_at TIMESTAMPTZ DEFAULT NOW(),
    note TEXT,
    UNIQUE(user_id, checkin_date)
);

CREATE INDEX IF NOT EXISTS idx_checkins_user_date ON gym_checkins(user_id, checkin_date);
CREATE INDEX IF NOT EXISTS idx_checkins_date ON gym_checkins(checkin_date);
