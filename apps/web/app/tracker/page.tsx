import { EmptyState } from "@/components/empty-state";
import { ApplicationsTable } from "@/components/applications-table";
import { getApplications } from "@/lib/jobs";

export default async function TrackerPage() { const rows = await getApplications(); return <div className="mx-auto max-w-7xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Application tracker</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Your pipeline</h1><p className="mt-3 text-slate-500">Track preparation, applications, interviews, offers, and closed roles.</p><div className="mt-8">{rows.length ? <ApplicationsTable rows={rows as Parameters<typeof ApplicationsTable>[0]["rows"]} /> : <EmptyState title="Your pipeline is clear" body="Save a role, then move it through your application stages." />}</div></div>; }
