-- Proactive messages (queued for delivery on next app open)
CREATE TABLE IF NOT EXISTS proactive_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_proactive_messages_user_status
    ON proactive_messages(user_id, status) WHERE status = 'pending';

-- Scheduled actions (reminders, nudges, recurring check-ins)
CREATE TABLE IF NOT EXISTS scheduled_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    run_at TIMESTAMPTZ NOT NULL,
    rrule TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    qstash_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scheduled_actions_pending
    ON scheduled_actions(run_at) WHERE status = 'pending';
CREATE INDEX idx_scheduled_actions_user
    ON scheduled_actions(user_id);

-- RLS
ALTER TABLE proactive_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_actions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own proactive messages"
    ON proactive_messages FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can view their own scheduled actions"
    ON scheduled_actions FOR SELECT USING (auth.uid() = user_id);
