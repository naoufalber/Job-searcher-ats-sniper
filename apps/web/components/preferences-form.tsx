"use client";

import { useState } from "react";
import { savePreferences } from "@/app/onboarding/actions";
import { preferencesInputSchema } from "@/lib/validation";

type Props = { initial?: Partial<Record<"target_roles" | "target_locations" | "employment_types" | "remote_preferences" | "working_languages" | "keywords" | "exclusions", string[]>> & { min_salary?: number | null } };
const fields = [
  ["targetRoles", "target_roles", "Target roles", "Data Scientist, ML Engineer"],
  ["targetLocations", "target_locations", "Target locations", "Paris, Remote"],
  ["employmentTypes", "employment_types", "Employment types", "CDI, Full-time"],
  ["remotePreferences", "remote_preferences", "Remote preferences", "Remote, Hybrid"],
  ["workingLanguages", "working_languages", "Working languages", "English, French"],
  ["keywords", "keywords", "Keywords", "Python, SQL, machine learning"],
  ["exclusions", "exclusions", "Exclude", "Internship, sales"],
] as const;

function split(value: string) { return value.split(",").map((item) => item.trim()).filter(Boolean); }

export function PreferencesForm({ initial }: Props) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(fields.map(([key, dbKey]) => [key, (initial?.[dbKey] ?? []).join(", ")])));
  const [minSalary, setMinSalary] = useState(initial?.min_salary?.toString() ?? "");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setMessage("");
    const input = { targetRoles: split(values.targetRoles ?? ""), targetLocations: split(values.targetLocations ?? ""), employmentTypes: split(values.employmentTypes ?? ""), remotePreferences: split(values.remotePreferences ?? ""), workingLanguages: split(values.workingLanguages ?? ""), keywords: split(values.keywords ?? ""), exclusions: split(values.exclusions ?? ""), minSalary: minSalary ? Number(minSalary) : null };
    const parsed = preferencesInputSchema.safeParse(input);
    if (!parsed.success) { setMessage(parsed.error.issues[0]?.message ?? "Check your preferences."); setPending(false); return; }
    const result = await savePreferences(parsed.data);
    setMessage(result.ok ? "Preferences saved." : result.error ?? "Unable to save."); setPending(false);
  }
  return <form className="space-y-5" onSubmit={submit}>{fields.map(([key, , label, placeholder]) => <label className="block text-sm font-medium text-ink" key={key}>{label}<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" placeholder={placeholder} value={values[key] ?? ""} onChange={(event) => setValues({ ...values, [key]: event.target.value })} /></label>)}<label className="block text-sm font-medium text-ink">Minimum annual salary<input className="focus-ring mt-2 w-full rounded-xl border border-line px-4 py-3 font-normal outline-none" min="0" type="number" value={minSalary} onChange={(event) => setMinSalary(event.target.value)} /></label><div className="flex items-center gap-4"><button className="focus-ring rounded-full bg-moss px-5 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Saving…" : "Save preferences"}</button>{message && <span className="text-sm text-slate-600" role="status">{message}</span>}</div></form>;
}
