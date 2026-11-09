"use client";

import { useState } from "react";
import { markJobSeen } from "@/app/actions";

export function SeenJobButton({ jobId, seenAt }: { jobId: string; seenAt?: string | null }) {
  const [seen, setSeen] = useState(Boolean(seenAt));
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    if (seen || busy) return;
    setBusy(true);
    const result = await markJobSeen(jobId);
    if (result.ok) setSeen(true);
    setBusy(false);
  }

  return <button className="focus-ring mt-2 rounded text-xs font-semibold text-slate-500 hover:text-moss disabled:cursor-default disabled:opacity-60" type="button" onClick={handleClick} disabled={seen || busy}>{seen ? "Seen" : busy ? "Saving…" : "Mark seen"}</button>;
}
