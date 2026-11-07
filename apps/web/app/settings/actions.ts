"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { profileInputSchema } from "@/lib/validation";

export async function updateProfile(input: unknown) {
  const parsed = profileInputSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid profile." };
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return { ok: false, error: "You must be signed in." };
  const { error } = await supabase.from("profiles").update({
    first_name: parsed.data.firstName,
    last_name: parsed.data.lastName,
    updated_at: new Date().toISOString(),
  }).eq("id", userData.user.id);
  if (error) return { ok: false, error: "Unable to update your profile." };
  revalidatePath("/settings");
  return { ok: true };
}
