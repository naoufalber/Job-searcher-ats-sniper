import { createClient } from "@/lib/supabase/server";

export type Profile = {
  id: string;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  updated_at: string;
};

export async function getCurrentProfile() {
  const supabase = createClient();
  if (!supabase) return { user: null, profile: null };
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return { user: null, profile: null };
  const { data: profile } = await supabase.from("profiles").select("id, email, first_name, last_name, created_at, updated_at").eq("id", userData.user.id).maybeSingle();
  return { user: userData.user, profile: profile as Profile | null };
}
