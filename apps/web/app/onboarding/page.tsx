import { redirect } from "next/navigation";
import { PreferencesForm } from "@/components/preferences-form";
import { getCurrentPreferences } from "@/lib/preferences";

export default async function OnboardingPage() {
  const preferences = await getCurrentPreferences();
  if (preferences?.onboarding_completed_at) redirect("/jobs");
  return <main className="mx-auto max-w-3xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Personal discovery</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Tune your job search</h1><p className="mt-3 max-w-2xl text-slate-500">These preferences stay private to your account and help organize the roles you review. Separate multiple values with commas.</p><section className="mt-8 rounded-2xl border border-line bg-white p-6"><PreferencesForm initial={preferences ?? undefined} /></section></main>;
}
