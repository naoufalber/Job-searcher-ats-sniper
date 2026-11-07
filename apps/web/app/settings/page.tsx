import { redirect } from "next/navigation";
import { ProfileForm } from "@/components/profile-form";
import { PasswordForm } from "@/components/password-form";
import { signOut } from "@/app/auth/actions";
import { getCurrentProfile } from "@/lib/profile";

export default async function SettingsPage() {
  const { user, profile } = await getCurrentProfile();
  if (!user) redirect("/login?next=/settings");
  const email = user.email ?? profile?.email ?? "";
  return <div className="mx-auto max-w-3xl px-6 py-12 lg:px-10"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Workspace settings</p><h1 className="mt-2 text-4xl font-semibold tracking-tight text-ink">Your account</h1><p className="mt-3 text-slate-500">Manage your identity and security without leaving the workspace.</p><section className="mt-8 rounded-2xl border border-line bg-white p-6"><h2 className="text-xl font-semibold text-ink">Personal information</h2><p className="mt-1 mb-6 text-sm text-slate-500">These details are stored in your user-owned profile.</p><ProfileForm email={email} firstName={profile?.first_name ?? ""} lastName={profile?.last_name ?? ""} /></section><section className="mt-6 rounded-2xl border border-line bg-white p-6"><h2 className="text-xl font-semibold text-ink">Security</h2><p className="mt-1 mb-6 text-sm text-slate-500">Re-enter your current password to confirm the change through Supabase Auth.</p><PasswordForm email={email} /></section><section className="mt-6 rounded-2xl border border-line bg-white p-6"><h2 className="text-xl font-semibold text-ink">Account</h2><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-slate-500">Authentication status</dt><dd className="mt-1 font-semibold text-emerald-700">Signed in</dd></div><div><dt className="text-slate-500">Created</dt><dd className="mt-1 font-semibold text-ink">{new Date(user.created_at).toLocaleDateString()}</dd></div></dl><form action={signOut} className="mt-6"><button className="focus-ring rounded-full border border-line px-5 py-3 text-sm font-semibold text-ink hover:border-moss" type="submit">Sign out</button></form></section></div>;
}
