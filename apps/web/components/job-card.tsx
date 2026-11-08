import Link from "next/link";
import type { Job } from "@/lib/types";

export function JobCard({ job }: { job: Job }) {
  const importKind = job.metadata?.import_kind;
  const provenance = importKind === "historical_sqlite"
    ? "Historical SQLite import"
    : importKind === "local_fixture" || job.metadata?.test === true
      ? "Local test fixture"
      : null;
  return (
    <article className="group rounded-2xl border border-line bg-white p-5 transition hover:-translate-y-0.5 hover:border-moss/50 hover:shadow-lg hover:shadow-slate-900/5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-moss">{job.company_name}</p>
          <h3 className="mt-2 text-lg font-semibold leading-7 text-ink">{job.title}</h3>
          {provenance && <span className="mt-2 inline-flex rounded-full bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">{provenance}</span>}
        </div>
        <span className="rounded-full bg-paper px-3 py-1 text-xs text-slate-500">{job.location ?? "Location not listed"}</span>
      </div>
      <div className="mt-6 flex items-center justify-between border-t border-line pt-4 text-sm text-slate-500">
        <span>{job.publication_date ? `Published ${new Date(job.publication_date).toLocaleDateString()}` : `Seen ${new Date(job.last_seen_at).toLocaleDateString()}`}</span>
        <Link className="focus-ring rounded font-medium text-moss group-hover:underline" href={`/jobs/${job.id}`}>View role →</Link>
      </div>
    </article>
  );
}
