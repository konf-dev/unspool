import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined

const isMockMode = !supabaseUrl || !supabasePublishableKey

const supabase: SupabaseClient | null = isMockMode
  ? null
  : createClient(supabaseUrl, supabasePublishableKey)

export { supabase, isMockMode }
