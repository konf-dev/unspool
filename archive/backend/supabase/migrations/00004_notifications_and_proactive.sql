-- Notification history + proactive messages
-- Replaces the boolean notification_sent_today with rich notification tracking

-- ============================================================
-- 1. notification_history — track what was sent and when
-- ============================================================
CREATE TABLE IF NOT EXISTS notification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    channel TEXT NOT NULL CHECK (channel IN ('push', 'proactive', 'email')),
    title TEXT,
    body TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_id UUID,
    delivered BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_notif_history_user
    ON notification_history(user_id, created_at DESC);

ALTER TABLE notification_history ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='notification_history' AND policyname='users_own_notif_history') THEN
    CREATE POLICY "users_own_notif_history" ON notification_history FOR ALL USING (auth.uid() = user_id);
  END IF;
END $$;

-- ============================================================
-- 2. proactive_messages — queued messages shown on next app open
-- ============================================================
CREATE TABLE IF NOT EXISTS proactive_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    content TEXT NOT NULL,
    priority INT DEFAULT 50,
    trigger_type TEXT NOT NULL,
    trigger_id UUID,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'expired')),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_proactive_user_pending
    ON proactive_messages(user_id, priority DESC)
    WHERE status = 'pending';

ALTER TABLE proactive_messages ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='proactive_messages' AND policyname='users_own_proactive') THEN
    CREATE POLICY "users_own_proactive" ON proactive_messages FOR ALL USING (auth.uid() = user_id);
  END IF;
END $$;

-- ============================================================
-- 3. Replace notification_sent_today with last_notification_at
-- ============================================================
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_notification_at TIMESTAMPTZ;
