"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/browser";
import { passwordChangeSchema } from "@/lib/validation";

export function PasswordForm({ email }: { email: string }) {
  const [values, setValues] = useState({ currentPassword: "", newPassword: "", confirmNewPassword: "" });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMessage("");
    const parsed = passwordChangeSchema.safeParse(values);
    if (!parsed.success) { setMessage(parsed.error.issues[0]?.message ?? "Check your password fields."); return; }
    setPending(true);
    try {
      const supabase = createClient();
      const reauth = await supabase.auth.signInWithPassword({ email, password: parsed.data.currentPassword });
      if (reauth.error) throw new Error("Current password is incorrect.");
      const updated = await supabase.auth.updateUser({ password: parsed.data.newPassword });
      if (updated.error) throw updated.error;
      setValues({ currentPassword: "", newPassword: "", confirmNewPassword: "" });
      setMessage("Password updated successfully.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to update your password."); }
    finally { setPending(false); }
  }
  return <form className="space-y-5" onSubmit={submit}><label className="block text-sm font-medium text-ink">Current password<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, currentPassword: event.target.value })} required type="password" value={values.currentPassword} /></label><label className="block text-sm font-medium text-ink">New password<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" minLength={8} onChange={(event) => setValues({ ...values, newPassword: event.target.value })} required type="password" value={values.newPassword} /></label><p className="text-xs leading-5 text-slate-500">Use at least 8 characters with an uppercase letter, lowercase letter, and number.</p><label className="block text-sm font-medium text-ink">Confirm new password<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, confirmNewPassword: event.target.value })} required type="password" value={values.confirmNewPassword} /></label><div className="flex items-center gap-4"><button className="focus-ring rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Updating…" : "Change password"}</button>{message && <span className="text-sm text-slate-600" role="status">{message}</span>}</div></form>;
}
