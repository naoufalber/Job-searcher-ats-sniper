"use client";

import { useState } from "react";
import { updateProfile } from "@/app/settings/actions";
import { profileInputSchema } from "@/lib/validation";

export function ProfileForm({ firstName, lastName, email }: { firstName: string; lastName: string; email: string }) {
  const [values, setValues] = useState({ firstName, lastName });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMessage("");
    const parsed = profileInputSchema.safeParse(values);
    if (!parsed.success) { setMessage(parsed.error.issues[0]?.message ?? "Check your profile fields."); return; }
    setPending(true);
    const result = await updateProfile(parsed.data);
    setMessage(result.ok ? "Personal information saved." : result.error ?? "Unable to save.");
    setPending(false);
  }
  return <form className="space-y-5" onSubmit={submit}><div className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-medium text-ink">First name<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, firstName: event.target.value })} required value={values.firstName} /></label><label className="text-sm font-medium text-ink">Last name<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, lastName: event.target.value })} required value={values.lastName} /></label></div><label className="block text-sm font-medium text-ink">Email address<input className="mt-2 w-full rounded-xl border border-line bg-paper px-4 py-3 font-normal text-slate-500" readOnly value={email} /></label><div className="flex items-center gap-4"><button className="focus-ring rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Saving…" : "Save changes"}</button>{message && <span className="text-sm text-slate-600" role="status">{message}</span>}</div></form>;
}
