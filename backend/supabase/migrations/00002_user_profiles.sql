-- User profiles with preferences and pattern data
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    timezone TEXT DEFAULT 'UTC',
    tone_preference TEXT DEFAULT 'casual',
    length_preference TEXT DEFAULT 'medium',
    pushiness_preference TEXT DEFAULT 'gentle',
    uses_emoji BOOLEAN DEFAULT false,
    primary_language TEXT DEFAULT 'en',
    patterns JSONB DEFAULT '{}'::jsonb,
    last_interaction_at TIMESTAMPTZ,
    last_proactive_at TIMESTAMPTZ,
    notification_sent_today BOOLEAN DEFAULT false,
    feed_token TEXT DEFAULT encode(gen_random_bytes(32), 'hex'),
    email_alias TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_profiles_email_alias ON user_profiles(email_alias) WHERE email_alias IS NOT NULL;
CREATE INDEX idx_user_profiles_feed_token ON user_profiles(feed_token);

-- Auto-create profile on Supabase auth signup
CREATE OR REPLACE FUNCTION public.on_auth_user_created()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, display_name)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email))
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.on_auth_user_created();

-- RLS
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own profile"
    ON user_profiles FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile"
    ON user_profiles FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can insert their own profile"
    ON user_profiles FOR INSERT WITH CHECK (auth.uid() = id);
