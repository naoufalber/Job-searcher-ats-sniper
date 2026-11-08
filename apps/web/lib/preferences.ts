import { createClient } from "@/lib/supabase/server";

export type UserPreferences = {
  user_id: string;
  target_roles: string[];
  target_locations: string[];
  employment_types: string[];
  remote_preferences: string[];
  working_languages: string[];
  keywords: string[];
  exclusions: string[];
  min_salary: number | null;
  onboarding_completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export async function getCurrentPreferences() {
  const supabase = createClient();
  if (!supabase) return null;
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return null;
  const { data } = await supabase.from("user_preferences").select("*").eq("user_id", userData.user.id).maybeSingle();
  return data as UserPreferences | null;
}
