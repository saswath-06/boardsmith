// Singleton Supabase client. Both env vars are public-safe — they're
// guarded server-side by Postgres RLS. The anon key is designed to ship
// in the browser bundle.
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!url || !anonKey) {
  // Fail loud at import time so missing config doesn't manifest as a
  // confusing 401 later.
  throw new Error(
    "Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Copy frontend/.env.example to frontend/.env.local and fill in your project values.",
  );
}

export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true, // pick up #access_token=... after OAuth redirect
  },
});
