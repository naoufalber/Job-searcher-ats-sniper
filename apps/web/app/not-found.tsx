import Link from "next/link";

export default function NotFound() { return <div className="mx-auto max-w-xl px-6 py-24 text-center"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Not found</p><h1 className="mt-3 text-4xl font-semibold text-ink">That role is unavailable.</h1><p className="mt-4 text-slate-500">It may have been removed from the active collection.</p><Link className="focus-ring mt-8 inline-flex rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white" href="/jobs">Back to discovery</Link></div>; }
