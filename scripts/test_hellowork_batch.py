"""Read-only HelloWork batch verification and optional local ingestion."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.parse

import requests

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ats_sniper


TARGET_URL = "https://www.hellowork.com/fr-fr/emplois/84704589.html"


def read_candidates(db_path: str, limit: int):
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            """
            SELECT job_id, company, title, url, detected_at
            FROM seen_jobs
            WHERE job_id LIKE 'hw_%' AND url <> ?
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (TARGET_URL, limit),
        ).fetchall()
    finally:
        conn.close()
    seen = set()
    result = []
    for row in rows:
        if row[3] in seen:
            continue
        seen.add(row[3])
        result.append(row)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--db", default=os.getenv("ATS_DB_FILE", "jobs_seen.db"))
    parser.add_argument("--ingest", action="store_true")
    args = parser.parse_args()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": "https://www.hellowork.com/",
    })
    api_url = os.getenv("ATS_INGESTION_API_URL", "").rstrip("/")
    secret = os.getenv("ATS_INGESTION_SHARED_SECRET", "")
    if args.ingest and (urllib.parse.urlparse(api_url).hostname not in {"127.0.0.1", "localhost", "::1"} or not secret):
        print("ERROR: --ingest requires a local API URL and shared secret")
        return 2
    candidate_limit = min(max(args.limit, 1), 10)
    candidates = read_candidates(args.db, candidate_limit)
    if not candidates:
        try:
            discovery = session.get(
                "https://www.hellowork.com/fr-fr/emploi/recherche.html",
                params={"k": "data", "l": "France", "p": 1}, timeout=20,
            )
            discovery.raise_for_status()
            candidates = [
                (f"hw_{offer['id']}", offer["company"], offer["title"], offer["url"], "fresh")
                for offer in ats_sniper.parse_hellowork_offers(discovery.text)
                if offer["url"] != TARGET_URL
            ][:candidate_limit]
            print(json.dumps({"discovery": "fresh", "candidates": len(candidates)}, ensure_ascii=False))
        except requests.RequestException as exc:
            print(f"ERROR: fresh HelloWork discovery failed: {type(exc).__name__}: {exc}")
            return 1
    results = []
    for job_id, company, title, url, detected_at in candidates:
        row = {"job_id": job_id, "company": company, "title": title, "url": url, "status": None}
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            row["http_status"] = response.status_code
            row["final_url"] = response.url
            response.raise_for_status()
            detail = ats_sniper.extract_hellowork_job_detail(response.text)
            description = detail.get("description") or ""
            row.update({
                "company": detail.get("company") or company,
                "title": detail.get("title") or title,
                "description_length": len(description),
                "complete": ats_sniper.is_description_complete(description),
                "method": "HelloWork JobPosting JSON-LD" if description else "none",
            })
            if not description:
                row.update(status="incomplete", reason="No JobPosting description")
            elif not row["complete"]:
                row.update(status="incomplete", reason="Below completeness threshold")
            else:
                row["status"] = "complete"
                if args.ingest:
                    payload = ats_sniper.build_ingestion_payload(
                        job_id, row["company"], row["title"], detail.get("location") or "France",
                        response.url, "HelloWork", description,
                    )
                    ingested = session.post(
                        f"{api_url}/api/ingest/jobs",
                        headers={"X-ATS-Ingestion-Secret": secret}, json=payload, timeout=10,
                    )
                    ingested.raise_for_status()
                    row["ingestion"] = "stored"
        except requests.RequestException as exc:
            row.update(status="http_error", reason=f"{type(exc).__name__}: {str(exc)[:220]}")
        results.append(row)
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    complete = sum(1 for row in results if row.get("status") == "complete")
    print(json.dumps({"tested": len(results), "complete": complete, "success_percent": round(100 * complete / len(results), 1) if results else 0, "ingest": args.ingest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
