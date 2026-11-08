"use client";

import { useEffect, useState } from "react";

type AnalysisResult = {
  score: number;
  confidence: string;
  matching_skills: { skill: string; evidence: string }[];
  missing_required_skills: string[];
  experience_gaps: string[];
  education_gaps: string[];
  language_location_considerations: string[];
  explanation: string;
  cv_adaptation_suggestions: string[];
  recommended_action: string;
};

type AnalysisResponse = { analysis?: { status?: string; result?: AnalysisResult }; queue?: { status?: string; last_error?: string | null } };

export function AnalyzeJobButton({ jobId }: { jobId: string }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);

  function applyResponse(body: AnalysisResponse) {
    if (body.analysis?.status === "completed" && body.analysis.result) setAnalysis(body.analysis.result);
    if (body.queue?.status === "failed") setMessage(body.queue.last_error ?? "Analysis failed.");
  }

  useEffect(() => {
    void fetch(`/api/ai/analyze?jobId=${encodeURIComponent(jobId)}`).then((response) => response.json()).then((body: AnalysisResponse) => applyResponse(body)).catch(() => undefined);
  }, [jobId]);

  async function analyze() {
    setBusy(true);
    setMessage("");
    const response = await fetch("/api/ai/analyze", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jobId }) });
    const body = await response.json() as AnalysisResponse & { error?: string };
    if (!response.ok) { setMessage(body.error ?? "Analysis unavailable."); setBusy(false); return; }
    if (body.analysis?.status === "completed" && body.analysis.result) { setAnalysis(body.analysis.result); setMessage("Loaded cached analysis."); setBusy(false); return; }
    setMessage("Queued for analysis…");
    for (let attempt = 0; attempt < 15; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      const progress = await fetch(`/api/ai/analyze?jobId=${encodeURIComponent(jobId)}`);
      const current = await progress.json() as AnalysisResponse;
      if (current.analysis?.status === "completed" && current.analysis.result) { setAnalysis(current.analysis.result); setMessage("Analysis complete."); setBusy(false); return; }
      if (current.queue?.status === "failed") { setMessage(current.queue.last_error ?? "Analysis failed."); setBusy(false); return; }
    }
    setMessage("Still queued. You can return later to view the result.");
    setBusy(false);
  }

  return <div className="mt-4"><button type="button" disabled={busy} onClick={() => void analyze()} className="rounded-full border border-moss px-4 py-2 text-sm font-semibold text-moss disabled:opacity-50">{busy ? "Analyzing…" : analysis ? "View CV match" : "Analyze against my CV"}</button>{message && <p className="mt-2 text-sm text-slate-600">{message}</p>}{analysis && <section className="mt-6 rounded-2xl border border-moss/30 bg-emerald-50/40 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold text-ink">CV match: {analysis.score}/100</h2><span className="rounded-full bg-white px-3 py-1 text-sm font-semibold text-moss">{analysis.recommended_action}</span></div><p className="mt-2 text-sm text-slate-600">Confidence: {analysis.confidence}</p><p className="mt-4 text-sm leading-6 text-slate-700">{analysis.explanation}</p><div className="mt-5 grid gap-4 md:grid-cols-2"><div><h3 className="font-semibold text-ink">Matching skills</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{analysis.matching_skills.map((item) => <li key={item.skill}><strong>{item.skill}</strong>{item.evidence && ` — ${item.evidence}`}</li>)}</ul></div><div><h3 className="font-semibold text-ink">Missing required skills</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{analysis.missing_required_skills.map((item) => <li key={item}>{item}</li>)}</ul></div></div>{analysis.cv_adaptation_suggestions.length > 0 && <div className="mt-5"><h3 className="font-semibold text-ink">CV improvement suggestions</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{analysis.cv_adaptation_suggestions.map((item) => <li key={item}>{item}</li>)}</ul></div>}</section>}</div>;
}
