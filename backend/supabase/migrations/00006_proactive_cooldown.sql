-- Add last_proactive_at to user_profiles to support cooldowns
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_proactive_at TIMESTAMPTZ;
