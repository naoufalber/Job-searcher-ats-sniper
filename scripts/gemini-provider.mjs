export async function requestGemini({ useMock, mockResponse, modelId, prompt, apiKey, fetchImpl = fetch }) {
  if (useMock) {
    return { ok: true, status: 200, headers: new Headers(), json: async () => ({ candidates: [{ content: { parts: [{ text: mockResponse }] } }] }) };
  }
  return fetchImpl(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(modelId)}:generateContent?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0, responseMimeType: "application/json" } }),
    signal: AbortSignal.timeout(30_000),
  });
}
