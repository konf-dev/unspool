-- Add 'executing' to scheduled_actions status constraint for atomic claim pattern
ALTER TABLE scheduled_actions DROP CONSTRAINT IF EXISTS scheduled_actions_status_check;
ALTER TABLE scheduled_actions ADD CONSTRAINT scheduled_actions_status_check
  CHECK (status IN ('pending', 'executing', 'executed', 'cancelled', 'failed'));

-- Add last_proactive_at column to user_profiles for proactive message cooldown
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_proactive_at TIMESTAMPTZ;
