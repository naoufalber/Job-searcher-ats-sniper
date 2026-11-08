"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/browser";
import { signupSchema } from "@/lib/validation";

export default function LoginPage() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next")?.startsWith("/") ? searchParams.get("next") : "/";
  const origin = typeof window === "undefined" ? "http://127.0.0.1:3000" : window.location.origin;
  const callback = `${origin}/auth/callback?next=${encodeURIComponent(next ?? "/")}`;
  const recoveryCallback = `${origin}/auth/callback?next=${encodeURIComponent("/auth/update-password")}`;
  const [mode, setMode] = useState<"login" | "signup" | "recovery">(searchParams.get("mode") === "signup" ? "signup" : "login");
  const [values, setValues] = useState({ firstName: "", lastName: "", email: "", password: "", confirmPassword: "" });
  const [message, setMessage] = useState(searchParams.get("error") ? "This authentication link is invalid or expired. Request a new one." : "");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setMessage("");
    try {
      const supabase = createClient();
      if (mode === "signup") {
        const parsed = signupSchema.safeParse(values);
        if (!parsed.success) { setMessage(parsed.error.issues[0]?.message ?? "Check your registration details."); return; }
        const signupCallback = `${origin}/auth/callback?next=${encodeURIComponent("/onboarding")}`;
        const result = await supabase.auth.signUp({ email: parsed.data.email, password: parsed.data.password, options: { emailRedirectTo: signupCallback, data: { first_name: parsed.data.firstName, last_name: parsed.data.lastName } } });
        if (result.error) throw result.error;
        setMessage("Check the local inbox to confirm your email before signing in.");
      } else if (mode === "recovery") {
        const result = await supabase.auth.resetPasswordForEmail(values.email, { redirectTo: recoveryCallback });
        if (result.error) throw result.error;
        setMessage("Check the local inbox for a password recovery link.");
      } else {
        const result = await supabase.auth.signInWithPassword({ email: values.email, password: values.password });
        if (result.error) throw result.error;
        window.location.assign(next ?? "/");
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : "Authentication failed."); }
    finally { setPending(false); }
  }
  const title = mode === "signup" ? "Create your workspace" : mode === "recovery" ? "Recover your account" : "Sign in to ATS Sniper";
  return <div className="mx-auto max-w-md px-6 py-20"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-moss">Your workspace</p><h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">{title}</h1><p className="mt-4 leading-7 text-slate-500">Use your account to save roles and track applications. Local emails are captured in Mailpit.</p><form className="mt-8 space-y-4 rounded-2xl border border-line bg-white p-6" onSubmit={submit}>{mode === "signup" && <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium text-ink">First name<input autoComplete="given-name" className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, firstName: event.target.value })} required value={values.firstName} /></label><label className="block text-sm font-medium text-ink">Last name<input autoComplete="family-name" className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, lastName: event.target.value })} required value={values.lastName} /></label></div>}<label className="block text-sm font-medium text-ink">Email address<input autoComplete="email" className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, email: event.target.value })} required type="email" value={values.email} /></label>{mode !== "recovery" && <><label className="block text-sm font-medium text-ink">Password<input autoComplete={mode === "signup" ? "new-password" : "current-password"} className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" minLength={8} onChange={(event) => setValues({ ...values, password: event.target.value })} required type="password" value={values.password} /></label>{mode === "signup" && <><label className="block text-sm font-medium text-ink">Confirm password<input autoComplete="new-password" className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" onChange={(event) => setValues({ ...values, confirmPassword: event.target.value })} required type="password" value={values.confirmPassword} /></label><p className="text-xs leading-5 text-slate-500">Use at least 8 characters with uppercase, lowercase, and a number.</p></>}</>}<button className="focus-ring w-full rounded-xl bg-moss px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Working…" : mode === "signup" ? "Create account" : mode === "recovery" ? "Send recovery link" : "Sign in"}</button>{message && <p className="text-sm leading-6 text-slate-600" role="status">{message}</p>}</form><div className="mt-6 flex flex-wrap gap-4 text-sm text-moss"><button className="focus-ring rounded underline-offset-4 hover:underline" onClick={() => { setMode(mode === "signup" ? "login" : "signup"); setMessage(""); }} type="button">{mode === "signup" ? "Already have an account? Sign in" : "Create an account"}</button>{mode !== "recovery" && <button className="focus-ring rounded underline-offset-4 hover:underline" onClick={() => { setMode("recovery"); setMessage(""); }} type="button">Forgot password?</button>}{mode === "recovery" && <button className="focus-ring rounded underline-offset-4 hover:underline" onClick={() => { setMode("login"); setMessage(""); }} type="button">Back to sign in</button>}</div><p className="mt-8 text-sm text-slate-500"><Link className="text-moss underline" href="/">Return home</Link></p></div>;
}
