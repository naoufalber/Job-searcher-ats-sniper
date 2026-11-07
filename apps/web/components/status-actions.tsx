"use client";

import { useState } from "react";
import { updateJobStatus } from "@/app/actions";
import type { JobStatus } from "@/lib/types";

export function StatusActions({ jobId }: { jobId: string }) {
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function setStatus(status: JobStatus) { setPending(true); const result = await updateJobStatus(jobId, status); setMessage(result.ok ? "Updated" : result.error ?? "Unable to update"); setPending(false); }
  return <div className="mt-8 flex flex-wrap items-center gap-2"><button className="focus-ring rounded-full border border-line px-4 py-2 text-sm font-semibold text-ink hover:border-moss" disabled={pending} onClick={() => setStatus("saved")}>Save role</button><button className="focus-ring rounded-full bg-moss px-4 py-2 text-sm font-semibold text-white" disabled={pending} onClick={() => setStatus("applied")}>Mark applied</button>{message && <span className="text-sm text-slate-500" role="status">{message}</span>}</div>;
}
