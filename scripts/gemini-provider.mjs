const stringList = { type: "ARRAY", items: { type: "STRING" }, maxItems: 30 };
export const analysisResponseSchema = {
  type: "OBJECT",
  properties: {
    score: { type: "INTEGER", minimum: 0, maximum: 100 },
    confidence: { type: "STRING", enum: ["low", "medium", "high"] },
    matching_skills: { type: "ARRAY", maxItems: 30, items: {
      type: "OBJECT", properties: { skill: { type: "STRING" }, evidence: { type: "STRING" } }, required: ["skill", "evidence"],
    } },
    missing_required_skills: stringList,
    experience_gaps: stringList,
    education_gaps: stringList,
    language_location_considerations: stringList,
    explanation: { type: "STRING" },
    cv_adaptation_suggestions: stringList,
    recommended_action: { type: "STRING", enum: ["Apply", "Review", "Low priority"] },
    contract_type: { type: "STRING", nullable: true, enum: ["CDI", "CDD", "Internship", "Apprenticeship", "Freelance", "Temporary", "Permanent", "Fixed-term", "Other"] },
    contract_evidence: { type: "STRING", nullable: true },
  },
  required: ["score", "confidence", "matching_skills", "missing_required_skills", "experience_gaps", "education_gaps", "language_location_considerations", "explanation", "cv_adaptation_suggestions", "recommended_action", "contract_type", "contract_evidence"],
};

export async function requestGemini({ useMock, mockResponse, modelId, prompt, apiKey, fetchImpl = fetch }) {
  if (useMock) {
    return { ok: true, status: 200, headers: new Headers(), json: async () => ({ candidates: [{ content: { parts: [{ text: mockResponse }] } }] }) };
  }
  return fetchImpl(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(modelId)}:generateContent?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: analysisResponseSchema } }),
    signal: AbortSignal.timeout(30_000),
  });
}
