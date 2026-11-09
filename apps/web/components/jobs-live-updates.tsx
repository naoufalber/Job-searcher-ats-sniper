"use client";

import { useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";

export function JobsLiveUpdates() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  useEffect(() => {
    const timer = window.setInterval(() => {
      const editing = document.activeElement?.matches("input,textarea,select,[contenteditable=true]");
      if (!pending && document.visibilityState === "visible" && !editing) {
        startTransition(() => router.refresh());
      }
    }, 20000);
    return () => window.clearInterval(timer);
  }, [router, pending]);
  return <p className="mt-3 text-xs text-slate-500" role="status">{pending ? "Updating scores..." : "Live updates on. Scores appear automatically as matching completes."}</p>;
}
