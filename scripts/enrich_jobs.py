"""Conservative, resumable enrichment for jobs already in local Supabase.

This script never touches jobs_seen.db and never sends notifications. It uses
public provider APIs/detail pages only; a failed provider request is recorded
on the job and does not stop other jobs.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

MIN_DESCRIPTION_CHARS = 240
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def is_complete_description(value: str | None) -> bool:
    text = clean_html(value)
    if not text or len(text) < MIN_DESCRIPTION_CHARS:
        return False
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    section_signals = sum(bool(re.search(pattern, text, re.I)) for pattern in (
        r"responsib", r"qualif", r"requirement", r"mission", r"profil", r"about the role",
    ))
    return sentence_count >= 3 or section_signals >= 2


def first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def jsonld_from_html(markup: str) -> dict[str, Any]:
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', markup, re.I | re.S):
        try:
            value = json.loads(html.unescape(raw.strip()))
        except json.JSONDecodeError:
            continue
        candidates = value if isinstance(value, list) else value.get("@graph", []) if isinstance(value, dict) else []
        if isinstance(value, dict):
            candidates = [value, *candidates]
        for candidate in candidates:
            if isinstance(candidate, dict) and (candidate.get("@type") == "JobPosting" or "description" in candidate):
                return candidate
    return {}


@dataclass
class Enriched:
    description: str | None = None
    description_source: str | None = None
    location: str | None = None
    remote_type: str | None = None
    contract_type: str | None = None
    publication_date: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    required_skills: list[str] | None = None


def from_jsonld(data: dict[str, Any]) -> Enriched:
    location = first(data.get("jobLocation")) or {}
    address = location.get("address", {}) if isinstance(location, dict) else {}
    parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
    salary = data.get("baseSalary") or {}
    value = salary.get("value", {}) if isinstance(salary, dict) else {}
    return Enriched(
        description=clean_html(data.get("description")),
        description_source="public_jsonld",
        location=", ".join(str(part) for part in parts if part),
        contract_type=str(first(data.get("employmentType")) or "") or None,
        publication_date=data.get("datePosted"),
        salary_min=value.get("minValue") if isinstance(value, dict) else None,
        salary_max=value.get("maxValue") if isinstance(value, dict) else None,
        salary_currency=(salary.get("currency") if isinstance(salary, dict) else None),
    )


def provider_from(source: str, url: str) -> str:
    aliases = {
        "sr": "smartrecruiters", "smartrecruiters": "smartrecruiters",
        "wd": "workday", "workday": "workday", "gh": "greenhouse",
        "greenhouse": "greenhouse", "lever": "lever", "ashby": "ashby",
        "hellowork": "hellowork", "welcome_to_the_jungle": "welcome_to_the_jungle",
    }
    source_key = source.strip().lower().replace("-", "_").replace(" ", "_")
    if source_key in aliases:
        return aliases[source_key]
    value = f"{source} {url}".lower()
    for name, tokens in {
        "smartrecruiters": ("smartrecruit",), "lever": ("lever.co",),
        "greenhouse": ("greenhouse",), "ashby": ("ashby",),
        "workday": ("workday",), "hellowork": ("hellowork",),
        "welcome_to_the_jungle": ("welcome", "jungle", "wttj"),
    }.items():
        if any(token in value for token in tokens):
            return name
    return source.lower().replace(" ", "_")


class Client:
    def __init__(self, base_url: str, service_key: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.dry_run = dry_run

    def request(self, path: str, method: str = "GET", body: Any = None) -> Any:
        url = self.base_url + path
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=payload, method=method, headers={
            "apikey": self.service_key, "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json", "Accept": "application/json",
        })
        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    raw = response.read().decode()
                    return json.loads(raw) if raw else None
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                if attempt >= MAX_RETRIES:
                    raise
                time.sleep(2 ** attempt)

    def jobs(self) -> list[dict[str, Any]]:
        path = "/rest/v1/jobs?select=id,canonical_url,description,description_status,description_source,location,remote_type,contract_type,publication_date,metadata,is_active,enrichment_error,job_sources(external_job_id,source_url,sources(name))&is_active=eq.true&order=first_seen_at.asc"
        return self.request(path) or []

    def update(self, job_id: str, fields: dict[str, Any]) -> None:
        if self.dry_run:
            return
        self.request(f"/rest/v1/jobs?id=eq.{urllib.parse.quote(job_id)}", "PATCH", fields)


def fetch_public(url: str, kind: str) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "ATS-Sniper-local-enrichment/1.0", "Accept": "application/json,text/html;q=0.9"})
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode(errors="replace"), response.headers.get("Content-Type", "")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to fetch {kind}")


def extract_json_or_page(provider: str, job: dict[str, Any]) -> Enriched:
    url = job.get("canonical_url") or ""
    if not url.startswith(("https://", "http://")):
        raise ValueError("canonical URL is not HTTP(S)")
    source_url = ((job.get("job_sources") or [{}])[0] or {}).get("source_url") or url
    parsed = urllib.parse.urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if provider == "smartrecruiters" and len(path_parts) >= 2:
        source_url = f"https://api.smartrecruiters.com/v1/companies/{path_parts[-2]}/postings/{path_parts[-1]}"
    elif provider == "greenhouse" and len(path_parts) >= 2 and path_parts[-2] == "jobs":
        source_url = f"https://boards-api.greenhouse.io/v1/jobs/{path_parts[-1]}?content=true"
    elif provider == "lever" and len(path_parts) >= 2:
        source_url = f"https://api.lever.co/v0/postings/{path_parts[-2]}?mode=json"
    elif provider == "ashby" and len(path_parts) >= 2:
        source_url = f"https://api.ashbyhq.com/posting-api/job-board/{path_parts[-2]}"
    raw, content_type = fetch_public(source_url, provider)
    if "json" in content_type or raw.lstrip().startswith(("{", "[")):
        data = json.loads(raw)
        if provider == "smartrecruiters":
            sections = data.get("jobAd", {}).get("sections", [])
            description = " ".join(str(section.get("content", "")) for section in sections if isinstance(section, dict))
            return Enriched(description=clean_html(description), description_source="smartrecruiters_public_api")
        if provider == "greenhouse":
            return Enriched(description=clean_html(data.get("content")), description_source="greenhouse_public_api", location=(data.get("location") or {}).get("name"))
        if provider == "lever":
            jobs = data if isinstance(data, list) else [data]
            match = next((item for item in jobs if str(item.get("id")) in url), jobs[0] if jobs else {})
            return Enriched(description=clean_html(" ".join((match.get("descriptionPlain", ""), match.get("additionalPlain", "")))), description_source="lever_public_api", location=(match.get("categories") or {}).get("location"))
        if provider == "ashby":
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            match = next((item for item in jobs if str(item.get("jobUrl", "")) == url or str(item.get("id", "")) in url), jobs[0] if jobs else {})
            return Enriched(description=clean_html(match.get("descriptionPlain")), description_source="ashby_public_api", location=match.get("location"))
        return Enriched(description=clean_html(data.get("descriptionPlain") or data.get("description") or data.get("content")), description_source=f"{provider}_public_api")
    return from_jsonld(jsonld_from_html(raw))


def merge_fields(job: dict[str, Any], enriched: Enriched) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if is_complete_description(enriched.description) and not is_complete_description(job.get("description")):
        fields.update(description=enriched.description, description_status="available", description_source=enriched.description_source)
    elif not is_complete_description(job.get("description")):
        status = "extraction_failed" if enriched.description else "provider_unavailable"
        reason = "Public content was below the completeness threshold." if enriched.description else "No complete public description was returned."
        fields.update(description_status=status, description_source=enriched.description_source, enrichment_error=reason)
    for name in ("location", "remote_type", "contract_type", "publication_date", "salary_min", "salary_max", "salary_currency", "required_skills"):
        value = getattr(enriched, name)
        if value not in (None, "", [] ) and not job.get(name):
            fields[name] = value
    if "enrichment_error" not in fields:
        fields["enrichment_error"] = None
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich existing local Supabase jobs without touching the collector database.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--provider")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    base_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "http://127.0.0.1:54321")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    host = urllib.parse.urlparse(base_url).hostname
    if host not in ALLOWED_LOCAL_HOSTS:
        raise SystemExit("Refusing non-local Supabase URL; this command is local-only.")
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY is required; the value is never logged.")
    client = Client(f"{base_url}", key, args.dry_run)
    jobs = client.jobs()
    selected = []
    for job in jobs:
        link = (job.get("job_sources") or [{}])[0] or {}
        source = ((link.get("sources") or {}).get("name") or "")
        provider = provider_from(source, job.get("canonical_url", ""))
        if provider in {"local_integration", "local_fixture"} or (job.get("metadata") or {}).get("test") is True:
            continue
        requested_provider = provider_from(args.provider or "", "") if args.provider else None
        if requested_provider and provider != requested_provider:
            continue
        if is_complete_description(job.get("description")):
            continue
        if job.get("enrichment_error") and not args.retry_failed:
            continue
        selected.append((job, provider))
    selected = selected[: max(0, min(args.limit, 5 if not args.dry_run else args.limit))]
    counts: dict[str, int] = {}
    for job, provider in selected:
        try:
            enriched = extract_json_or_page(provider, job)
            fields = merge_fields(job, enriched)
            client.update(job["id"], fields)
            counts[provider] = counts.get(provider, 0) + int("description" in fields)
            print(f"{'DRY-RUN ' if args.dry_run else ''}job={job['id']} provider={provider} description={'yes' if 'description' in fields else 'no'}")
        except Exception as exc:
            client.update(job["id"], {"description_status": "provider_unavailable", "enrichment_error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            print(f"job={job['id']} provider={provider} failed={type(exc).__name__}")
    print(json.dumps({"eligible_selected": len(selected), "descriptions_added": sum(counts.values()), "by_provider": counts, "dry_run": args.dry_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
