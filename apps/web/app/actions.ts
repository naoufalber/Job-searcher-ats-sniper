"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import type { ApplicationStatus, JobStatus } from "@/lib/types";
import { applicationUpdateSchema } from "@/lib/validation";

const statuses = new Set<JobStatus>(["new", "saved", "applied", "rejected", "archived"]);

export async function updateJobStatus(jobId: string, status: JobStatus) {
  if (!/^[0-9a-f-]{36}$/i.test(jobId) || !statuses.has(status)) {
    return { ok: false, error: "Invalid job status request." };
  }
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data } = await supabase.auth.getUser();
  if (!data.user) return { ok: false, error: "You must be signed in." };
  const applicationStatus = status === "applied" ? "applied" : status === "saved" ? "to_review" : "to_review";
  const { error } = await supabase.from("user_job_status").upsert({ user_id: data.user.id, job_id: jobId, status, application_status: applicationStatus, applied_at: status === "applied" ? new Date().toISOString() : null, updated_at: new Date().toISOString() });
  if (error) return { ok: false, error: "Unable to update this role." };
  revalidatePath("/jobs");
  revalidatePath("/saved");
  revalidatePath("/tracker");
  return { ok: true };
}

export async function updateApplication(input: unknown) {
  const parsed = applicationUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid application details." };
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return { ok: false, error: "You must be signed in." };
  const value = parsed.data;
  const appliedAt = value.applicationStatus === "applied" && !value.nextFollowUpAt ? new Date().toISOString() : value.applicationStatus === "applied" ? new Date().toISOString() : null;
  const legacyStatus: JobStatus = value.applicationStatus === "rejected" ? "rejected" : value.applicationStatus === "closed" || value.applicationStatus === "withdrawn" ? "archived" : value.applicationStatus === "applied" || value.applicationStatus === "interview" || value.applicationStatus === "offer" ? "applied" : "saved";
  const { error } = await supabase.from("user_job_status").upsert({
    user_id: userData.user.id,
    job_id: value.jobId,
    status: legacyStatus,
    application_status: value.applicationStatus as ApplicationStatus,
    notes: value.notes,
    recruiter_contact: value.recruiterContact,
    next_follow_up_at: value.nextFollowUpAt ?? null,
    interview_at: value.interviewAt ?? null,
    cv_document_id: value.cvDocumentId ?? null,
    applied_at: appliedAt,
    updated_at: new Date().toISOString(),
  });
  if (error) return { ok: false, error: "Unable to update the application." };
  revalidatePath("/saved"); revalidatePath("/tracker"); revalidatePath(`/jobs/${value.jobId}`);
  return { ok: true };
}

export async function markJobSeen(jobId: string) {
  if (!/^[0-9a-f-]{36}$/i.test(jobId)) return { ok: false, error: "Invalid job." };
  const supabase = createClient();
  if (!supabase) return { ok: false, error: "Supabase is not configured." };
  const { data } = await supabase.auth.getUser();
  if (!data.user) return { ok: false, error: "You must be signed in." };
  const { error } = await supabase.from("user_job_seen").upsert({ user_id: data.user.id, job_id: jobId, seen_at: new Date().toISOString() }, { onConflict: "user_id,job_id" });
  if (error) return { ok: false, error: "Unable to mark this role as seen." };
  revalidatePath("/jobs");
  revalidatePath(`/jobs/${jobId}`);
  return { ok: true };
}
