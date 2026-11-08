"""Safely backfill historical SQLite jobs into the authenticated ingestion API.

The SQLite connection is read-only. This script never imports ats_sniper.py and
never calls notification providers. Use --dry-run first and --limit 1 for the
first real import.
"""

import argparse
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


def read_rows(database: Path):
    uri = database.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(seen_jobs)")]
        required = {"job_id", "company", "title", "url", "detected_at"}
        missing = required.difference(columns)
        if missing:
            raise RuntimeError(f"seen_jobs is missing columns: {sorted(missing)}")
        return connection.execute(
            "SELECT job_id, company, title, url, detected_at, notified_at, notification_status "
            "FROM seen_jobs ORDER BY detected_at, job_id"
        ).fetchall()


def source_for(job_id: str) -> str:
    match = re.match(r"^([a-z0-9]+)[_:/-]", job_id.lower())
    return match.group(1) if match else "historical_sqlite"


def timestamp(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def payload(row):
    job_id, company, title, url, detected_at, notified_at, status = row
    if not re.match(r"^https?://", url or "", re.IGNORECASE):
        return None
    return {
        "source": source_for(job_id),
        "external_job_id": job_id,
        "company_name": company,
        "title": title,
        "location": None,
        "country": None,
        "contract_type": None,
        "remote_type": None,
        "canonical_url": url,
        "description": None,
        "first_seen_at": timestamp(detected_at),
        "publication_date": None,
        "metadata": {
            "import_kind": "historical_sqlite",
            "historical_job_id": job_id,
            "historical_detected_at": detected_at,
            "historical_notification_status": status,
            "historical_notified_at": notified_at,
        },
    }


def report(rows):
    payloads = [payload(row) for row in rows]
    eligible = [item for item in payloads if item]
    print(json.dumps({
        "total_rows": len(rows),
        "eligible_rows": len(eligible),
        "skipped_rows": len(rows) - len(eligible),
        "sources": dict(Counter(item["source"] for item in eligible)),
        "missing_fields": {
            "location": len(eligible),
            "description": len(eligible),
            "publication_date": len(eligible),
            "contract_type": len(eligible),
        },
        "sample": eligible[:3],
    }, ensure_ascii=False, indent=2))
    return eligible


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("jobs_seen.db"))
    parser.add_argument("--api-url", default=os.getenv("ATS_INGESTION_API_URL", "").rstrip("/"))
    parser.add_argument("--secret", default=os.getenv("ATS_INGESTION_SHARED_SECRET", ""))
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--job-id")
    parser.add_argument("--exclude-job-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    rows = read_rows(args.db)
    eligible = report(rows)
    if args.job_id:
        eligible = [item for item in eligible if item["external_job_id"] == args.job_id]
    if args.exclude_job_id:
        excluded = set(args.exclude_job_id)
        eligible = [item for item in eligible if item["external_job_id"] not in excluded]
    selected = eligible[:args.limit]
    if args.dry_run:
        print(json.dumps({"selected": selected}, ensure_ascii=False, indent=2))
        return 0
    if not args.api_url or not args.secret:
        parser.error("--api-url/ATS_INGESTION_API_URL and --secret/ATS_INGESTION_SHARED_SECRET are required")
    for item in selected:
        response = requests.post(
            f"{args.api_url}/api/ingest/jobs",
            headers={"X-ATS-Ingestion-Secret": args.secret},
            json=item,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        print(json.dumps({"external_job_id": item["external_job_id"], "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
