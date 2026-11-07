"use client";

import { FormEvent, useState } from "react";
import { createClient } from "@/lib/supabase/browser";

export default function UpdatePasswordPage() {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setMessage("");
    try { const { error } = await createClient().auth.updateUser({ password }); if (error) throw error; setMessage("Password updated. You can continue to your workspace."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "This recovery link is invalid or expired."); }
    finally { setPending(false); }
  }
  return <div className="mx-auto max-w-md px-6 py-20"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Account recovery</p><h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">Choose a new password</h1><p className="mt-4 leading-7 text-slate-500">This page is available only after Supabase verifies a recovery link.</p><form className="mt-8 space-y-4 rounded-2xl border border-line bg-white p-6" onSubmit={submit}><label className="block text-sm font-medium text-ink" htmlFor="password">New password</label><input className="focus-ring w-full rounded-xl border border-line px-4 py-3 outline-none" id="password" minLength={8} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /><button className="focus-ring w-full rounded-xl bg-moss px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Updating…" : "Update password"}</button>{message && <p className="text-sm leading-6 text-slate-600" role="status">{message}</p>}</form></div>;
}
