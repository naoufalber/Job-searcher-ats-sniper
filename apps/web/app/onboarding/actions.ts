"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { preferencesInputSchema } from "@/lib/validation";

export async function savePreferences(input: unknown) {
  const parsed = preferencesInputSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid preferences." };
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return { ok: false, error: "You must be signed in." };
  const p = parsed.data;
  const preferencesUpdatedAt = new Date().toISOString();
  const { error } = await supabase.from("user_preferences").upsert({
    user_id: userData.user.id,
    target_roles: p.targetRoles,
    target_locations: p.targetLocations,
    employment_types: p.employmentTypes,
    remote_preferences: p.remotePreferences,
    working_languages: p.workingLanguages,
    keywords: p.keywords,
    exclusions: p.exclusions,
    min_salary: p.minSalary,
    onboarding_completed_at: new Date().toISOString(),
    updated_at: preferencesUpdatedAt,
  }, { onConflict: "user_id" });
  if (error) return { ok: false, error: "Unable to save your preferences." };
  const admin = createAdminClient();
  if (admin) await admin.from("matching_backfill_requests").upsert({ user_id: userData.user.id, preferences_updated_at: preferencesUpdatedAt, status: "pending" }, { onConflict: "user_id,preferences_updated_at" });
  revalidatePath("/onboarding");
  revalidatePath("/jobs");
  return { ok: true };
}
