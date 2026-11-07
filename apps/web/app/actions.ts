"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import type { JobStatus } from "@/lib/types";

const statuses = new Set<JobStatus>(["new", "saved", "applied", "rejected", "archived"]);

export async function updateJobStatus(jobId: string, status: JobStatus) {
  if (!/^[0-9a-f-]{36}$/i.test(jobId) || !statuses.has(status)) {
    return { ok: false, error: "Invalid job status request." };
  }
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data } = await supabase.auth.getUser();
  if (!data.user) return { ok: false, error: "You must be signed in." };
  const { error } = await supabase.from("user_job_status").upsert({ user_id: data.user.id, job_id: jobId, status, updated_at: new Date().toISOString() });
  if (error) return { ok: false, error: "Unable to update this role." };
  revalidatePath("/jobs");
  revalidatePath("/saved");
  revalidatePath("/tracker");
  return { ok: true };
}
