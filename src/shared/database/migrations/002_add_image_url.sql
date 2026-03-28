-- Add image_url column to gym_checkins for storing uploaded photos
ALTER TABLE gym_checkins ADD COLUMN IF NOT EXISTS image_url TEXT;
