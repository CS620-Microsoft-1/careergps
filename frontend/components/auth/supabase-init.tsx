"use client";

import { getSupabase } from "@/lib/supabase/client";

// Create the Supabase client as soon as the app loads in the browser, before any component's
// effects run, so every API call already sends the access token.
if (typeof window !== "undefined") {
  try {
    getSupabase();
  } catch (error) {
    console.error(error);
  }
}

export function SupabaseInit() {
  return null;
}
