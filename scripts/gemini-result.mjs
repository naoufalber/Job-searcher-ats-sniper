const ACTIONS = new Map([
  ["apply", "Apply"],
  ["review", "Review"],
  ["low priority", "Low priority"],
]);

const CONTRACTS = new Set(["CDI", "CDD", "Internship", "Apprenticeship", "Freelance", "Temporary", "Permanent", "Fixed-term", "Other"]);

export function verifiedContract(result, title, description) {
  const evidence = text(result.contract_evidence, 500);
  const normalize = (value) => String(value ?? "").normalize("NFKC").replace(/\s+/g, " ").trim().toLowerCase();
  if (!CONTRACTS.has(result.contract_type) || !evidence || !normalize(`${title}\n${description}`).includes(normalize(evidence))) {
    return { contract_type: null, contract_evidence: null };
  }
  return { contract_type: result.contract_type, contract_evidence: evidence };
}

function text(value, max) {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null;
}

function list(value, max, mapper = (item) => text(item, max)) {
  if (!Array.isArray(value)) return null;
  const result = value.map(mapper).filter(Boolean);
  return result.length <= 30 ? result : null;
}

function matchingSkills(value) {
  if (!Array.isArray(value) || value.length > 30) return null;
  const result = [];
  for (const item of value) {
    if (typeof item === "string") {
      const skill = text(item, 120);
      if (skill) result.push({ skill, evidence: "" });
      continue;
    }
    if (!item || typeof item !== "object") continue;
    const skill = text(item.skill ?? item.name, 120);
    const evidence = text(item.evidence ?? item.reason ?? item.description, 500) ?? "";
    if (skill) result.push({ skill, evidence });
  }
  return result;
}

function jsonObject(textValue) {
  const cleaned = String(textValue ?? "").replace(/```(?:json)?/gi, "").replace(/```/g, "").trim();
  const start = cleaned.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let quoted = false;
  let escaped = false;
  for (let index = start; index < cleaned.length; index += 1) {
    const char = cleaned[index];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === "{") depth += 1;
    else if (char === "}" && --depth === 0) {
      try { return JSON.parse(cleaned.slice(start, index + 1)); } catch { return null; }
    }
  }
  return null;
}

export function normalizeAnalysis(value) {
  if (!value || typeof value !== "object") return null;
  const v = value;
  const score = typeof v.score === "number" ? v.score : Number(v.score);
  const confidence = typeof v.confidence === "string" ? v.confidence.toLowerCase() : "";
  const recommendedAction = typeof (v.recommended_action ?? v.recommendation) === "string"
    ? ACTIONS.get((v.recommended_action ?? v.recommendation).trim().toLowerCase())
    : undefined;
  const matching = matchingSkills(v.matching_skills ?? v.matchingSkills);
  const missing = list(v.missing_required_skills ?? v.missing_skills, 120);
  const experience = list(v.experience_gaps ?? v.experience_gap, 300);
  const education = list(v.education_gaps ?? v.education_gap, 300);
  const languageLocation = list(v.language_location_considerations ?? v.language_or_location_considerations, 300);
  const explanation = text(v.explanation ?? v.summary, 1200);
  const suggestions = list(v.cv_adaptation_suggestions ?? v.suggestions, 500);
  if (!Number.isInteger(score) || score < 0 || score > 100) return null;
  if (!["low", "medium", "high"].includes(confidence) || !matching || !missing || !experience || !education || !languageLocation || !explanation || !suggestions || !recommendedAction) return null;
  const contract = "contract_type" in v ? { contract_type: CONTRACTS.has(v.contract_type) ? v.contract_type : null, contract_evidence: text(v.contract_evidence, 500) } : {};
  return { score, confidence, matching_skills: matching, missing_required_skills: missing, experience_gaps: experience, education_gaps: education, language_location_considerations: languageLocation, explanation, cv_adaptation_suggestions: suggestions, recommended_action: recommendedAction, ...contract };
}

export function parseAnalysisResponse(textValue) {
  return normalizeAnalysis(jsonObject(textValue));
}
