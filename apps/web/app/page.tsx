import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { listJobs } from "@/lib/jobs";
import { JobCard } from "@/components/job-card";

export default async function HomePage() {
  const jobs = await listJobs();
  return (
    <div className="mx-auto max-w-7xl px-6 py-16 lg:px-10 lg:py-24">
      <section className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-moss">Focused job discovery</p>
          <h1 className="mt-5 max-w-3xl font-display text-5xl leading-[1.02] tracking-tight text-ink sm:text-7xl">Find the roles worth your attention.</h1>
          <p className="mt-7 max-w-xl text-lg leading-8 text-slate-600">A calm, searchable workspace for jobs collected from the sources you already trust. No invented listings. No noisy scorecards.</p>
          <div className="mt-9 flex flex-wrap gap-3"><Link className="focus-ring rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#274b3e]" href="/jobs">Browse roles</Link><Link className="focus-ring rounded-full border border-line bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:border-moss" href="/login">Create your workspace</Link></div>
        </div>
        <div className="rounded-3xl border border-line bg-white p-7 shadow-[0_20px_70px_rgba(23,32,42,0.07)]"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Live workspace</p><div className="mt-8 grid grid-cols-2 gap-4"><div className="rounded-2xl bg-paper p-5"><p className="text-3xl font-semibold text-ink">{jobs.length || "—"}</p><p className="mt-2 text-sm text-slate-500">active roles loaded</p></div><div className="rounded-2xl bg-paper p-5"><p className="text-3xl font-semibold text-ink">{jobs.length ? "Ready" : "—"}</p><p className="mt-2 text-sm text-slate-500">data connection</p></div></div><p className="mt-7 text-sm leading-6 text-slate-500">The interface stays empty until your Supabase project contains real collected jobs.</p></div>
      </section>
      <section className="mt-24"><div className="mb-6 flex items-end justify-between"><div><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Latest roles</p><h2 className="mt-2 text-2xl font-semibold text-ink">Recently collected</h2></div><Link className="focus-ring rounded text-sm font-semibold text-moss hover:underline" href="/jobs">See all roles →</Link></div>{jobs.length ? <div className="grid gap-4 md:grid-cols-2">{jobs.slice(0, 4).map((job) => <JobCard key={job.id} job={job} />)}</div> : <EmptyState title="Your discovery feed is ready" body="Connect Supabase and run the collector integration to see real roles here." />}</section>
    </div>
  );
}
