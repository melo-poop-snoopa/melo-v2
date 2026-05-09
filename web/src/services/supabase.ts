import { createClient } from "@supabase/supabase-js";

const supabaseUrl =
  (import.meta.env.VITE_SUPABASE_URL as string | undefined) ??
  "http://127.0.0.1:54321";

const supabaseKey = import.meta.env.VITE_SUPABASE_KEY as string;

if (!supabaseKey) {
  console.warn(
    "VITE_SUPABASE_KEY is not set — Supabase operations will fail. Set it in .env"
  );
}

export const supabase = createClient(supabaseUrl, supabaseKey ?? "");
