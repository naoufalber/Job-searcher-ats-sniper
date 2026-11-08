"""Verify one public job-detail page and optionally ingest it locally."""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ats_sniper


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--ingest", action="store_true")
    args = parser.parse_args()
    if not args.url.startswith(("https://", "http://")):
        print("ERROR: only HTTP(S) URLs are allowed")
        return 2
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": "https://www.hellowork.com/",
    })
    try:
        response = session.get(args.url, timeout=20, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: HTTP request failed: {type(exc).__name__}: {exc}")
        return 1
    detail = ats_sniper.extract_hellowork_job_detail(response.text)
    description = detail.get("description") or ""
    method = "HelloWork JobPosting JSON-LD" if description else "none"
    preview = re.sub(r"\s+", " ", description)[:240]
    print(f"HTTP status: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"HTML length: {len(response.text)}")
    print(f"Job title: {detail.get('title') or 'unknown'}")
    print(f"Company: {detail.get('company') or 'unknown'}")
    print(f"Description characters: {len(description)}")
    print(f"Description complete: {ats_sniper.is_description_complete(description)}")
    print(f"Extraction method: {method}")
    print(f"Preview: {preview}")
    if not description:
        print("ERROR: no job description was extracted")
        return 1
    if args.ingest:
        api_url = os.getenv("ATS_INGESTION_API_URL", "").rstrip("/")
        secret = os.getenv("ATS_INGESTION_SHARED_SECRET", "")
        host = urllib.parse.urlparse(api_url).hostname if api_url else None
        if host not in {"127.0.0.1", "localhost", "::1"} or not secret:
            print("ERROR: --ingest requires a local ATS_INGESTION_API_URL and server-only shared secret")
            return 2
        match = re.search(r"/emplois/(\d+)", response.url)
        external_id = f"hw_{match.group(1)}" if match else f"hw_{abs(hash(response.url))}"
        payload = ats_sniper.build_ingestion_payload(
            external_id, detail.get("company") or "HelloWork", detail.get("title") or "HelloWork job",
            detail.get("location") or "France", response.url, "HelloWork", description,
        )
        ingest = session.post(
            f"{api_url}/api/ingest/jobs", headers={"X-ATS-Ingestion-Secret": secret},
            json=payload, timeout=10,
        )
        print(f"Ingestion status: {ingest.status_code}")
        print(f"Ingestion response: {ingest.text[:500]}")
        ingest.raise_for_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
