import html
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Sous Windows, une execution non interactive peut heriter de CP-1252 et
# planter au premier emoji avant meme l'envoi de la notification.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_FILE = os.getenv("ATS_DB_FILE", "jobs_seen.db")
REQUEST_TIMEOUT = int(os.getenv("ATS_REQUEST_TIMEOUT", "20"))
DETAIL_REQUEST_TIMEOUT = min(
    REQUEST_TIMEOUT,
    max(1, int(os.getenv("ATS_DETAIL_REQUEST_TIMEOUT", "8"))),
)
WORKDAY_MAX_PAGES = int(os.getenv("WORKDAY_MAX_PAGES", "100"))
PROVIDER_TIMEOUT_SECONDS = max(10, int(os.getenv("ATS_PROVIDER_TIMEOUT_SECONDS", "90")))
SCAN_TIMEOUT_SECONDS = max(
    PROVIDER_TIMEOUT_SECONDS,
    int(os.getenv("ATS_SCAN_TIMEOUT_SECONDS", "780")),
)
HELLOWORK_MAX_PAGES = int(os.getenv("HELLOWORK_MAX_PAGES", "2"))
HELLOWORK_LOCATION = os.getenv("HELLOWORK_LOCATION", "France")
HELLOWORK_QUERIES = tuple(
    query.strip()
    for query in os.getenv(
        "HELLOWORK_QUERIES",
        "data,data scientist,data engineer,machine learning,ai engineer,data analyst",
    ).split(",")
    if query.strip()
)
WTTJ_ENV_URL = "https://www.welcometothejungle.com/api/env"
WTTJ_SITE_ORIGIN = "https://www.welcometothejungle.com"
WTTJ_INDEX = "wttj_jobs_production_en"
WTTJ_ALGOLIA_APP_ID = os.getenv("WTTJ_ALGOLIA_APP_ID", "")
WTTJ_ALGOLIA_API_KEY = os.getenv("WTTJ_ALGOLIA_API_KEY", "")
WTTJ_FILTERS = os.getenv(
    "WTTJ_FILTERS", "offices.country_code:FR AND contract_type:full_time"
)
WTTJ_MAX_HITS = min(int(os.getenv("WTTJ_MAX_HITS", "200")), 1000)
WTTJ_QUERIES = tuple(
    query.strip()
    for query in os.getenv(
        "WTTJ_QUERIES",
        "data scientist,data engineer,machine learning,ai engineer,data analyst,data architect",
    ).split(",")
    if query.strip()
)
SCAN_INTERVAL_SECONDS = int(os.getenv("ATS_SCAN_INTERVAL_SECONDS", "300"))
INGESTION_API_URL = os.getenv("ATS_INGESTION_API_URL", "").strip().rstrip("/")
INGESTION_SHARED_SECRET = os.getenv("ATS_INGESTION_SHARED_SECRET", "")
INGESTION_TIMEOUT = min(int(os.getenv("ATS_INGESTION_TIMEOUT", "8")), REQUEST_TIMEOUT)
INGESTION_BATCH_SIZE = int(os.getenv("ATS_INGESTION_BATCH_SIZE", "50"))
INGESTION_ENRICH_DETAILS = os.getenv("ATS_INGESTION_ENRICH_DETAILS", "false").lower() == "true"
WEB_ONLY_MODE = False
WEB_ONLY_DETAIL_MAX_REQUESTS = int(os.getenv("ATS_WEB_ONLY_DETAIL_MAX_REQUESTS", "50"))
INGESTION_DETAIL_MAX_REQUESTS = max(1, int(os.getenv("ATS_INGESTION_DETAIL_MAX_REQUESTS", "10")))
HELLOWORK_DETAIL_MAX_REQUESTS = max(
    1, int(os.getenv("HELLOWORK_DETAIL_MAX_REQUESTS", "50"))
)
WEB_ONLY_MAX_JOBS = max(1, int(os.getenv("ATS_WEB_ONLY_MAX_JOBS", "50")))
WEB_ONLY_DETAIL_WORKERS = max(1, min(int(os.getenv("ATS_WEB_ONLY_DETAIL_WORKERS", "4")), 8))
WEB_ONLY_DETAIL_DELAY = max(0.0, float(os.getenv("ATS_WEB_ONLY_DETAIL_DELAY", "0.2")))
WEB_ONLY_DETAIL_CACHE = {}
WEB_ONLY_DETAIL_STATS = {}
WEB_ONLY_DETAIL_REQUESTS = 0
WEB_ONLY_DETAIL_REQUESTS_NEW = 0
WEB_ONLY_DETAIL_REQUESTS_EXISTING = 0
WEB_ONLY_ACCEPTED_JOBS = 0
WEB_ONLY_DETAIL_LAST_ERROR = {}
WEB_ONLY_ENRICH_MAX_ATTEMPTS = max(1, int(os.getenv("ATS_WEB_ONLY_ENRICH_MAX_ATTEMPTS", "4")))
SCAN_HAD_FAILURES = False


def log_event(event, provider=None, **fields):
    """Emit machine-readable progress without including URLs, payloads, or secrets."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
    }
    if provider:
        record["provider"] = provider
    record.update(fields)
    print("[ATS_EVENT] " + json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)


# Les textes sont normalises sans accents avant application des expressions.
POSITIVE_PATTERNS = [
    r"\bdata\s+(?:scientist|science|engineer|analyst)\b",
    r"\bdata\s+(?:architect|architecte|modeler|modelisation|quality|governance|platform|steward)\b",
    r"\bdata\s*(?:&|and|et)\s*(?:ai|ml|machine learning)\b",
    r"\b(?:architecte|consultant(?:e)?)\s+(?:data|data science|ia|ai)\b",
    r"\b(?:business intelligence|bi analyst|data product)\b",
    r"\bingenieur\s+(?:data|donnees?)\b",
    r"\banalytics?\s+engineer\b",
    r"\b(?:ai|ia|a\.i\.)\s+engineer\b",
    r"\bingenieur\s+(?:ai|ia|intelligence artificielle)\b",
    r"\bartificial intelligence\b",
    r"\b(?:generative\s+ai|genai|llm)\b",
    r"\bml\s*engineer\b",
    r"\bmachine learning\b",
    r"\bmlops\b",
    r"\bdeep learning\b",
]

NEGATIVE_PATTERNS = [
    r"\bstage\b", r"\bstagiaire\b", r"\bintern(?:ship)?\b",
    r"\balternan(?:ce|t|te)\b", r"\bapprenti(?:e|ssage)?\b",
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b",
    r"\bstaff\b", r"\bmanager\b", r"\bmanagement\b",
    r"\bteam\s+leader\b",
    r"\bdirecteur\b", r"\bdirector\b", r"\bhead\s+of\b", r"\bvp\b",
    r"\bchef\s+de\b", r"\bresponsable\b", r"\bexpert(?:e)?\b",
    r"\bexperimente(?:e)?\b", r"\bconfirme(?:e)?\b",
    r"\bexperienced\b", r"\bmid[- ]?level\b",
    r"\bpeople\s+data\b", r"\bworkday\b",
]

# Les ATS utilisent tantot le nom du pays, tantot le code ISO "FR".
LOCATION_PATTERNS = [
    r"\bfrance\b", r"\bfr\b", r"\bile[- ]de[- ]france\b", r"\bparis\b",
    r"\bla defense\b", r"\bputeaux\b", r"\bcourbevoie\b",
    r"\bmontrouge\b", r"\bmassy\b", r"\bsaint[- ]denis\b", r"\bissy\b",
    r"\bboulogne\b", r"\blevallois\b", r"\bneuilly\b", r"\bchatillon\b",
    r"\bivry\b", r"\blyon\b", r"\blille\b", r"\btoulouse\b",
    r"\bbordeaux\b", r"\bnantes\b", r"\brennes\b", r"\bnice\b",
    r"\bsophia[- ]antipolis\b", r"\bgrenoble\b", r"\bstrasbourg\b",
    r"\bmontpellier\b", r"\bmarseille\b", r"\baix[- ]en[- ]provence\b",
]


# Endpoints publics verifies. Les noms et les slugs sont separes.
SMARTRECRUITERS_COMPANIES = [
    ("Natixis", "Natixis"), ("Devoteam", "Devoteam"),
    ("Publicis Groupe", "PublicisGroupe"), ("Equativ", "Equativ"),
    ("Criteo", "Criteo"), ("Sia", "Sia"), ("BlaBlaCar", "BlaBlaCar"),
]
LEVER_COMPANIES = [("Mistral AI", "mistral"), ("Qonto", "qonto")]
GREENHOUSE_COMPANIES = [
    ("Artefact", "artefact"), ("Doctolib", "doctolib"),
    ("Datadog", "datadog"),
]
ASHBY_COMPANIES = [("Alan", "alan")]
WORKDAY_COMPANIES = [
    {
        "name": "Sanofi",
        "url": "https://sanofi.wd3.myworkdayjobs.com/wday/cxs/sanofi/SanofiCareers/jobs",
        "base_link": "https://sanofi.wd3.myworkdayjobs.com/fr-FR/SanofiCareers",
    },
    {
        "name": "Thales",
        "url": "https://thales.wd3.myworkdayjobs.com/wday/cxs/thales/Careers/jobs",
        "base_link": "https://thales.wd3.myworkdayjobs.com/fr-FR/Careers",
    },
]

# Leur ancien endpoint est invalide. Le bilan les signale explicitement au lieu
# de laisser croire qu'elles sont encore couvertes.
UNSUPPORTED_COMPANIES = [
    "AXA", "Capgemini", "Contentsquare", "Back Market", "Hugging Face",
    "ManoMano", "PayFit", "Spendesk",
]


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(
        char for char in value if not unicodedata.combining(char)
    ).lower()
    return normalized.replace("_", " ")


def create_http_session():
    session = requests.Session()
    retries = Retry(
        total=3, connect=3, read=3, backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "ATS-Job-Sniper/2.0"})
    return session


def create_ingestion_session():
    """Use queue-level retries instead of multiplying HTTP retries per scan."""
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
    session.headers.update({"User-Agent": "ATS-Job-Sniper/2.0"})
    return session


def request_json(session, method, url, source, **kwargs):
    raise_errors = kwargs.pop("_raise_errors", False)
    started = time.monotonic()
    log_event("request_start", source=source, method=method)
    timeout = kwargs.pop("_timeout", REQUEST_TIMEOUT)
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        payload = response.json()
        log_event(
            "request_success", source=source, method=method,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return payload
    except (requests.RequestException, ValueError) as exc:
        log_event(
            "request_error", source=source, method=method,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__, error=str(exc)[:200],
        )
        print(f"[ERREUR API] {source}: {exc}", flush=True)
        if raise_errors:
            raise
        return None


def request_text(session, method, url, source, **kwargs):
    raise_errors = kwargs.pop("_raise_errors", False)
    started = time.monotonic()
    log_event("request_start", source=source, method=method)
    timeout = kwargs.pop("_timeout", REQUEST_TIMEOUT)
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        log_event(
            "request_success", source=source, method=method,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return response.text
    except (requests.RequestException, AttributeError) as exc:
        log_event(
            "request_error", source=source, method=method,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__, error=str(exc)[:200],
        )
        print(f"[ERREUR HTTP] {source}: {exc}", flush=True)
        if raise_errors:
            raise
        return None


def normalize_job_description(value):
    if not value:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_jsonld_job_data(markup):
    decoded_markup = html.unescape(markup or "")
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        decoded_markup, re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(html.unescape(raw.strip()))
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = []
        if isinstance(payload, dict):
            candidates.append(payload)
            if isinstance(payload.get("@graph"), list):
                candidates.extend(payload["@graph"])
        elif isinstance(payload, list):
            candidates.extend(payload)
        for candidate in candidates:
            if isinstance(candidate, dict) and (
                candidate.get("@type") == "JobPosting" or candidate.get("description")
            ):
                return candidate
    return {}


def extract_jsonld_job_description(markup):
    data = extract_jsonld_job_data(markup)
    return normalize_job_description(data.get("description"))


def extract_hellowork_job_detail(markup):
    """Extract HelloWork's JobPosting JSON-LD, including HTML description."""
    data = extract_jsonld_job_data(markup)
    organization = data.get("hiringOrganization") or {}
    location = data.get("jobLocation") or {}
    address = location.get("address") if isinstance(location, dict) else {}
    return {
        "title": data.get("title"),
        "company": organization.get("name") if isinstance(organization, dict) else None,
        "description": normalize_job_description(data.get("description")),
        "location": ", ".join(
            str(value) for value in (
                (address or {}).get("addressLocality"),
                (address or {}).get("addressRegion"),
                (address or {}).get("addressCountry"),
            ) if value
        ),
        "publication_date": data.get("datePosted"),
        "contract_type": data.get("employmentType"),
    }


def is_description_complete(description):
    text = normalize_job_description(description)
    if len(text) < 240:
        return False
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    section_signals = sum(
        bool(re.search(pattern, text, re.IGNORECASE))
        for pattern in (r"responsib", r"qualif", r"requirement", r"mission", r"profil", r"avantage")
    )
    return sentence_count >= 3 or section_signals >= 2


def _path_parts(url):
    return [part for part in urllib.parse.urlparse(url).path.split("/") if part]


def fetch_web_only_description(provider, url, session, existing_job=False):
    """Fetch permitted public detail data for the explicit ingestion/web-only paths."""
    if not (WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS) or not url:
        return ""
    global WEB_ONLY_DETAIL_REQUESTS, WEB_ONLY_DETAIL_REQUESTS_NEW, WEB_ONLY_DETAIL_REQUESTS_EXISTING
    if url in WEB_ONLY_DETAIL_CACHE:
        return WEB_ONLY_DETAIL_CACHE[url]
    provider_key = re.sub(r"[^a-z0-9]+", "_", provider.lower()).strip("_")
    detail_limit = WEB_ONLY_DETAIL_MAX_REQUESTS if WEB_ONLY_MODE else INGESTION_DETAIL_MAX_REQUESTS
    if provider_key == "hellowork":
        detail_limit = max(detail_limit, HELLOWORK_DETAIL_MAX_REQUESTS)
    if existing_job:
        detail_limit = min(detail_limit, INGESTION_DETAIL_MAX_REQUESTS)
        if WEB_ONLY_DETAIL_REQUESTS_EXISTING >= detail_limit:
            WEB_ONLY_DETAIL_LAST_ERROR[url] = "Detail request budget deferred"
            return ""
        WEB_ONLY_DETAIL_REQUESTS_EXISTING += 1
    else:
        if WEB_ONLY_DETAIL_REQUESTS_NEW >= detail_limit:
            WEB_ONLY_DETAIL_LAST_ERROR[url] = "Detail request budget deferred"
            return ""
        WEB_ONLY_DETAIL_REQUESTS_NEW += 1
    WEB_ONLY_DETAIL_REQUESTS += 1
    if WEB_ONLY_DETAIL_DELAY:
        time.sleep(WEB_ONLY_DETAIL_DELAY)
    parts = _path_parts(url)
    try:
        value = ""
        if provider_key == "smartrecruiters" and len(parts) >= 2:
            data = request_json(
                session, "GET",
                f"https://api.smartrecruiters.com/v1/companies/{parts[-2]}/postings/{parts[-1]}",
                "SmartRecruiters/detail", _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True,
            ) or {}
            sections = (data.get("jobAd") or {}).get("sections") or []
            if isinstance(sections, dict):
                sections = sections.values()
            value = "\n\n".join(str(section.get("content", "")) for section in sections if isinstance(section, dict))
        elif provider_key == "lever" and len(parts) >= 2:
            data = request_json(
                session, "GET", f"https://api.lever.co/v0/postings/{parts[-2]}",
                "Lever/detail", params={"mode": "json"}, _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True,
            ) or []
            jobs = data if isinstance(data, list) else [data]
            match = next((job for job in jobs if str(job.get("id", "")) in url), jobs[0] if jobs else {})
            value = "\n\n".join((match.get("descriptionPlain", ""), match.get("additionalPlain", "")))
        elif provider_key == "greenhouse" and len(parts) >= 2:
            data = request_json(
                session, "GET", f"https://boards-api.greenhouse.io/v1/jobs/{parts[-1]}",
                "Greenhouse/detail", params={"content": "true"}, _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True,
            ) or {}
            value = data.get("content", "")
        elif provider_key == "ashby" and len(parts) >= 2:
            data = request_json(
                session, "GET", f"https://api.ashbyhq.com/posting-api/job-board/{parts[-2]}",
                "Ashby/detail", _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True,
            ) or {}
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            match = next((job for job in jobs if str(job.get("jobUrl", "")) == url or str(job.get("id", "")) in url), jobs[0] if jobs else {})
            value = match.get("descriptionPlain", "")
        elif provider_key == "hellowork":
            markup = request_text(
                session, "GET", url, "HelloWork/detail", _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True
            ) or ""
            value = extract_hellowork_job_detail(markup).get("description", "")
        elif provider_key in {"workday", "welcome_to_the_jungle"}:
            markup = request_text(
                session, "GET", url, f"{provider}/detail", _timeout=DETAIL_REQUEST_TIMEOUT, _raise_errors=True
            ) or ""
            value = extract_jsonld_job_description(markup)
        description = normalize_job_description(value)
        if not description:
            WEB_ONLY_DETAIL_LAST_ERROR[url] = "Provider response contained no extractable job description."
        WEB_ONLY_DETAIL_CACHE[url] = description
        stats = WEB_ONLY_DETAIL_STATS.setdefault(provider_key, {"attempted": 0, "with_description": 0, "failed": 0})
        stats["attempted"] += 1
        if description:
            stats["with_description"] += 1
        return description
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        WEB_ONLY_DETAIL_CACHE[url] = ""
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        WEB_ONLY_DETAIL_LAST_ERROR[url] = (
            f"Provider detail request returned HTTP {status}." if status
            else f"Description request failed: {type(exc).__name__}."
        )
        stats = WEB_ONLY_DETAIL_STATS.setdefault(provider_key, {"attempted": 0, "with_description": 0, "failed": 0})
        stats["attempted"] += 1
        stats["failed"] += 1
        print(f"[WEB ONLY][DETAIL {provider}] {type(exc).__name__}: {str(exc)[:200]}")
        return ""


def web_only_enrichment_due(conn, job_id, url):
    if not (WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS):
        return False
    row = conn.execute(
        "SELECT status, attempts, next_attempt_at, adapter_revision FROM web_only_enrichment WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    revision = 2 if urllib.parse.urlparse(url).hostname == "jobs.smartrecruiters.com" else 1
    if not row:
        conn.execute(
            "INSERT OR IGNORE INTO web_only_enrichment(job_id, url, updated_at, adapter_revision) VALUES (?, ?, ?, ?)",
            (job_id, url, datetime.now(timezone.utc).isoformat(), revision),
        )
        conn.commit()
        return True
    status, attempts, next_attempt_at, previous_revision = row
    if status != "complete" and previous_revision < revision:
        conn.execute(
            "UPDATE web_only_enrichment SET status = 'pending', attempts = 0, next_attempt_at = NULL, adapter_revision = ? WHERE job_id = ?",
            (revision, job_id),
        )
        conn.commit()
        return True
    if status in {"complete", "terminal"} or attempts >= WEB_ONLY_ENRICH_MAX_ATTEMPTS:
        return False
    if not next_attempt_at:
        return True
    try:
        return datetime.fromisoformat(next_attempt_at) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def record_web_only_enrichment(conn, job_id, url, description):
    now = datetime.now(timezone.utc)
    if not description and WEB_ONLY_DETAIL_LAST_ERROR.get(url) == "Detail request budget deferred":
        conn.execute(
            "UPDATE web_only_enrichment SET status = 'retry', next_attempt_at = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
            ((now + timedelta(seconds=300)).isoformat(), "Detail request budget deferred", now.isoformat(), job_id),
        )
        conn.commit()
        return
    if description:
        conn.execute(
            """
            UPDATE web_only_enrichment
            SET url = ?, status = 'complete', attempts = attempts + 1,
                next_attempt_at = NULL, last_error = NULL, updated_at = ?
            WHERE job_id = ?
            """,
            (url, now.isoformat(), job_id),
        )
    else:
        row = conn.execute(
            "SELECT attempts FROM web_only_enrichment WHERE job_id = ?", (job_id,)
        ).fetchone()
        attempts = (row[0] if row else 0) + 1
        terminal = attempts >= WEB_ONLY_ENRICH_MAX_ATTEMPTS
        delay = min(86_400, 300 * (2 ** min(attempts - 1, 5)))
        conn.execute(
            """
            UPDATE web_only_enrichment
            SET url = ?, status = ?, attempts = ?, next_attempt_at = ?,
                last_error = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                url, "terminal" if terminal else "retry", attempts,
                None if terminal else (now + timedelta(seconds=delay)).isoformat(),
                WEB_ONLY_DETAIL_LAST_ERROR.get(url) or "No description returned",
                now.isoformat(), job_id,
            ),
        )
    conn.commit()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            notified_at TEXT,
            notification_status TEXT NOT NULL DEFAULT 'pending'
        )
        """
    )
    if WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_only_enrichment (
                job_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error TEXT,
                adapter_revision INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        enrichment_columns = {row[1] for row in conn.execute("PRAGMA table_info(web_only_enrichment)")}
        if "adapter_revision" not in enrichment_columns:
            conn.execute("ALTER TABLE web_only_enrichment ADD COLUMN adapter_revision INTEGER NOT NULL DEFAULT 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supabase_ingestion_queue (
            job_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            sent_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT,
            last_error TEXT
        )
        """
    )
    ingestion_columns = {row[1] for row in conn.execute("PRAGMA table_info(supabase_ingestion_queue)")}
    if "delivered_description" not in ingestion_columns:
        conn.execute("ALTER TABLE supabase_ingestion_queue ADD COLUMN delivered_description TEXT")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "notified_at" not in columns:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN notified_at TEXT")
    if "notification_status" not in columns:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN notification_status TEXT")
        conn.execute(
            "UPDATE seen_jobs SET notification_status = 'sent' "
            "WHERE notification_status IS NULL"
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    return conn, count == 0


def queue_job(conn, job_id, company, title, url):
    existing = conn.execute(
        "SELECT notification_status FROM seen_jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    if existing:
        return existing[0] == "pending"
    conn.execute(
        """
        INSERT INTO seen_jobs
            (job_id, company, title, url, detected_at, notification_status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (job_id, company, title, url, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return True


def mark_job(conn, job_id, status):
    notified_at = datetime.now(timezone.utc).isoformat() if status == "sent" else None
    conn.execute(
        "UPDATE seen_jobs SET notification_status = ?, notified_at = ? WHERE job_id = ?",
        (status, notified_at, job_id),
    )
    conn.commit()


def ingestion_enabled():
    return bool(INGESTION_API_URL and INGESTION_SHARED_SECRET)


def ingestion_timestamp(value=None):
    parsed = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_ingestion_payload(job_id, company, title, location, url, ats_source,
                            description="", experience_level=""):
    source = re.sub(r"[^a-z0-9]+", "_", ats_source.lower()).strip("_")
    location_value = (location or "").strip() or None
    country = "France" if re.search(r"\b(?:france|fr)\b", location_value or "", re.IGNORECASE) else None
    manager_search_url, recruiter_search_url = build_xray_links(company)
    return {
        "source": source,
        "external_job_id": str(job_id),
        "company_name": company,
        "title": title,
        "location": location_value,
        "country": country,
        "contract_type": None,
        "remote_type": "remote" if re.search(r"\bremote\b", location_value or "", re.IGNORECASE) else None,
        "canonical_url": url,
        "description": description or None,
        "first_seen_at": ingestion_timestamp(),
        "publication_date": None,
        "metadata": {
            "description_extraction": {
                "reason": None if description else WEB_ONLY_DETAIL_LAST_ERROR.get(url) or "No extraction details recorded yet.",
            },
            "experience_level": experience_level or None,
            "contacts": {
                "manager_search_url": manager_search_url,
                "recruiter_search_url": recruiter_search_url,
            },
        },
    }


def queue_ingestion(conn, payload):
    if not ingestion_enabled():
        return
    queued_at = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT payload_json, status, delivered_description FROM supabase_ingestion_queue WHERE job_id = ?",
        (payload["external_job_id"],),
    ).fetchone()
    refresh_sent = False
    if existing:
        previous_payload = json.loads(existing[0])
        if previous_payload.get("description") and not payload.get("description"):
            payload = {**payload, "description": previous_payload["description"]}
        refresh_sent = (
            existing[1] == "sent" and (
                (bool(payload.get("description")) and payload.get("description") != existing[2])
                or ((payload.get("metadata") or {}).get("description_extraction") != (previous_payload.get("metadata") or {}).get("description_extraction"))
            )
        )
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    conn.execute(
        """
        INSERT INTO supabase_ingestion_queue
            (job_id, payload_json, queued_at, status, attempts, next_attempt_at, last_error)
        VALUES (?, ?, ?, 'pending', 0, NULL, NULL)
        ON CONFLICT(job_id) DO UPDATE SET
            payload_json = excluded.payload_json
        """,
        (payload["external_job_id"], payload_json, queued_at),
    )
    if refresh_sent:
        conn.execute(
            """UPDATE supabase_ingestion_queue
               SET status = 'pending', next_attempt_at = NULL, last_error = NULL
               WHERE job_id = ? AND status = 'sent'""",
            (payload["external_job_id"],),
        )
    conn.commit()


def try_queue_ingestion(conn, job_id, company, title, location, url,
                        ats_source, description="", experience_level=""):
    """Best-effort ingestion boundary; never interrupts notifications."""
    global SCAN_HAD_FAILURES
    if not ingestion_enabled():
        return
    try:
        payload = build_ingestion_payload(
            job_id, company, title, location, url, ats_source,
            description, experience_level,
        )
        if not description and (WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS):
            state = conn.execute("SELECT last_error FROM web_only_enrichment WHERE job_id = ?", (job_id,)).fetchone()
            if state and state[0]:
                payload["metadata"]["description_extraction"]["reason"] = state[0]
        queue_ingestion(conn, payload)
    except Exception as exc:  # Keep failures isolated to the additive path.
        SCAN_HAD_FAILURES = True
        print(f"[ERREUR SUPABASE] Mise en file ignoree: {type(exc).__name__}: {str(exc)[:300]}")


def flush_ingestion_queue(conn, session, deadline=None):
    global SCAN_HAD_FAILURES
    if not ingestion_enabled():
        return 0
    try:
        now = datetime.now(timezone.utc)
        rows = conn.execute(
            """
            SELECT job_id, payload_json, attempts
            FROM supabase_ingestion_queue
            WHERE status = 'pending'
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY CASE WHEN sent_at IS NULL THEN 0 ELSE 1 END, queued_at
            LIMIT ?
            """,
            (now.isoformat(), INGESTION_BATCH_SIZE),
        ).fetchall()
    except Exception as exc:
        SCAN_HAD_FAILURES = True
        print(f"[ERREUR SUPABASE] Lecture de file ignoree: {type(exc).__name__}: {str(exc)[:300]}")
        return 0
    sent = 0
    for job_id, payload_json, attempts in rows:
        if deadline is not None and time.monotonic() >= deadline:
            log_event("ingestion_flush_deadline", pending_batch=len(rows) - sent)
            break
        try:
            payload = json.loads(payload_json)
            if payload.get("first_seen_at"):
                payload["first_seen_at"] = ingestion_timestamp(payload["first_seen_at"])
            response = session.post(
                f"{INGESTION_API_URL}/api/ingest/jobs",
                headers={"X-ATS-Ingestion-Secret": INGESTION_SHARED_SECRET},
                json=payload,
                timeout=INGESTION_TIMEOUT,
            )
            response.raise_for_status()
            acknowledgment = response.json()
            if isinstance(acknowledgment, dict):
                log_event(
                    "ingestion_delivered", external_job_id=job_id,
                    job_id=acknowledgment.get("job_id"),
                    description_status=acknowledgment.get("description_status"),
                    auto_match=acknowledgment.get("auto_match"),
                )
        except (requests.RequestException, ValueError) as exc:
            SCAN_HAD_FAILURES = True
            log_event("ingestion_delivery_failed", job_id=job_id, error_type=type(exc).__name__)
            next_attempt = now + timedelta(
                seconds=min(900, 30 * (2 ** min(attempts + 1, 5)))
            )
            try:
                conn.execute(
                    """
                    UPDATE supabase_ingestion_queue
                    SET attempts = attempts + 1, next_attempt_at = ?, last_error = ?, status = 'pending'
                    WHERE job_id = ?
                    """,
                    (next_attempt.isoformat(), str(exc)[:500], job_id),
                )
            except Exception as db_exc:
                print(f"[ERREUR SUPABASE] Echec mise a jour retry: {type(db_exc).__name__}: {str(db_exc)[:300]}")
            continue
        try:
            conn.execute(
                """
                UPDATE supabase_ingestion_queue
                SET status = 'sent', sent_at = ?, next_attempt_at = NULL, last_error = NULL,
                    delivered_description = ?
                WHERE job_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), payload.get("description") or "", job_id),
            )
        except Exception as exc:
            print(f"[ERREUR SUPABASE] Echec confirmation: {type(exc).__name__}: {str(exc)[:300]}")
            continue
        sent += 1
    try:
        conn.commit()
    except Exception as exc:
        print(f"[ERREUR SUPABASE] Commit de file ignore: {type(exc).__name__}: {str(exc)[:300]}")
    return sent


def matches_criteria(title, location, description="", experience_level=""):
    title_text = normalize_text(title)
    location_text = normalize_text(location)
    description_text = normalize_text(description)
    experience_text = normalize_text(experience_level)
    if not any(re.search(pattern, location_text) for pattern in LOCATION_PATTERNS):
        return False
    if any(re.search(pattern, title_text) for pattern in NEGATIVE_PATTERNS):
        return False
    if not any(re.search(pattern, title_text) for pattern in POSITIVE_PATTERNS):
        return False
    if re.search(r"\b(?:mid[- _]?senior|senior|director|executive)\b", experience_text):
        return False
    too_experienced = re.search(
        r"(?:minimum|min\.?|at least|au moins|experience.{0,25})\s*"
        r"(?:de\s+)?(?:4|5|6|7|8|9|[1-9]\d)\+?\s*(?:ans|years)",
        description_text,
    )
    return too_experienced is None


def build_xray_links(company):
    company_clean = company.replace("-", " ")
    manager_query = (
        f'site:fr.linkedin.com/in/ "{company_clean}" '
        '("Head of Data" OR "Lead Data" OR "Manager Data" OR '
        '"Head of AI" OR "Data Science Manager")'
    )
    recruiter_query = (
        f'site:fr.linkedin.com/in/ "{company_clean}" '
        '("Talent Acquisition" OR "Recruteur" OR "Recruiter") '
        '("Data" OR "Tech" OR "IT")'
    )
    return (
        "https://www.google.com/search?q=" + urllib.parse.quote(manager_query),
        "https://www.google.com/search?q=" + urllib.parse.quote(recruiter_query),
    )


def send_alert(company, title, location, url, ats_source, session=None):
    session = session or create_http_session()
    manager_url, recruiter_url = build_xray_links(company)
    now_text = datetime.now().astimezone().strftime("%d/%m/%Y a %H:%M")
    delivered = False
    discord_message = (
        f"🚨 **NOUVELLE OFFRE DATA/IA ({ats_source})** 🚨\n"
        f"🏢 **Entreprise :** {company}\n"
        f"💼 **Poste :** {title}\n"
        f"📍 **Lieu :** {location}\n"
        f"⚡ **Postuler :** {url}\n\n"
        f"🎯 **[Manager Data sur LinkedIn]({manager_url})**\n"
        f"🕵️ **[Recruteur Tech sur LinkedIn]({recruiter_url})**\n"
        f"⏱️ *Detectee le {now_text}*"
    )
    print("\n" + "=" * 55)
    print(discord_message)
    print("=" * 55)

    if DISCORD_WEBHOOK_URL:
        try:
            response = session.post(
                DISCORD_WEBHOOK_URL, json={"content": discord_message},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            delivered = True
        except requests.RequestException as exc:
            print(f"[ERREUR DISCORD] {exc}")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        telegram_message = (
            f"🚨 <b>NOUVELLE OFFRE DATA/IA ({html.escape(ats_source)})</b> 🚨\n"
            f"🏢 <b>Entreprise :</b> {html.escape(company)}\n"
            f"💼 <b>Poste :</b> {html.escape(title)}\n"
            f"📍 <b>Lieu :</b> {html.escape(location)}\n"
            f'⚡ <a href="{html.escape(url, quote=True)}">Postuler</a>\n\n'
            f'🎯 <a href="{html.escape(manager_url, quote=True)}">Manager Data</a>\n'
            f'🕵️ <a href="{html.escape(recruiter_url, quote=True)}">Recruteur Tech</a>\n'
            f"⏱️ Detectee le {now_text}"
        )
        try:
            response = session.post(
                telegram_url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": telegram_message,
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            delivered = True
        except requests.RequestException as exc:
            print(f"[ERREUR TELEGRAM] {exc}")

    if not DISCORD_WEBHOOK_URL and not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[ERREUR CONFIG] Aucun canal de notification n'est configure.")
    return delivered


def process_job(conn, job_id, company, title, location, url, ats_source,
                silent_init, session, description="", experience_level=""):
    global WEB_ONLY_ACCEPTED_JOBS
    if not matches_criteria(title, location, "", experience_level):
        return 0
    already_seen = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
    ).fetchone() is not None
    # Detail enrichment is additive and independently backoff-controlled. It
    # must also revisit already-seen offers, otherwise rows discovered before
    # enrichment was enabled can remain permanently without descriptions.
    should_enrich = WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS
    if should_enrich and not description:
        try:
            if web_only_enrichment_due(conn, job_id, url):
                description = fetch_web_only_description(
                    ats_source, url, session, existing_job=already_seen
                )
                record_web_only_enrichment(conn, job_id, url, description)
            else:
                description = WEB_ONLY_DETAIL_CACHE.get(url, "")
        except Exception as exc:
            WEB_ONLY_DETAIL_LAST_ERROR[url] = f"Description extraction failed: {type(exc).__name__}."
            log_event("job_enrichment_error", provider=ats_source, error_type=type(exc).__name__)
    if not description and ingestion_enabled():
        try:
            cached = conn.execute(
                "SELECT payload_json FROM supabase_ingestion_queue WHERE job_id = ?", (job_id,)
            ).fetchone()
            if cached:
                description = json.loads(cached[0]).get("description") or ""
        except Exception as exc:
            log_event("ingestion_description_cache_error", error_type=type(exc).__name__)
    if not matches_criteria(title, location, description, experience_level):
        return 0
    if WEB_ONLY_MODE and WEB_ONLY_ACCEPTED_JOBS >= WEB_ONLY_MAX_JOBS:
        return 0
    queued = queue_job(conn, job_id, company, title, url)
    if not queued:
        if WEB_ONLY_MODE or INGESTION_ENRICH_DETAILS:
            try_queue_ingestion(
                conn, job_id, company, title, location, url, ats_source,
                description, experience_level,
            )
            print(f"[WEB ONLY] Enriched existing job: {company} - {title}")
        return 0
    if WEB_ONLY_MODE:
        WEB_ONLY_ACCEPTED_JOBS += 1
    if not already_seen:
        log_event("job_discovered", provider=ats_source, external_job_id=job_id,
                  company=company, title=title, description_length=len(description or ""))
    try_queue_ingestion(
        conn, job_id, company, title, location, url, ats_source,
        description, experience_level,
    )
    if silent_init or WEB_ONLY_MODE:
        mark_job(conn, job_id, "baseline")
        prefix = "[WEB ONLY]" if WEB_ONLY_MODE else "[INITIALISATION]"
        print(f"{prefix} {company} - {title}")
        return 1
    if send_alert(company, title, location, url, ats_source, session):
        mark_job(conn, job_id, "sent")
        return 1
    # L'etat pending provoque une nouvelle tentative au prochain scan.
    return 0


class HelloworkOfferParser(HTMLParser):
    """Extracts the server-rendered offer cards from a HelloWork search page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.offers = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        if attributes.get("data-cy") != "offerTitle":
            return
        href = attributes.get("href", "")
        title_attr = html.unescape(attributes.get("title", "")).strip()
        aria_label = html.unescape(attributes.get("aria-label", "")).strip()
        if not href or not title_attr:
            return

        title, separator, company = title_attr.rpartition(" - ")
        if not separator:
            title, company = title_attr, "HelloWork"
        location_match = re.search(
            r"\b(?:a|à)\s+(.+?),\s+chez\s+", aria_label, re.IGNORECASE
        )
        location = location_match.group(1).strip() if location_match else "France"
        job_id_match = re.search(r"/emplois/(\d+)\.html", href)
        job_id = job_id_match.group(1) if job_id_match else href
        self.offers.append({
            "id": job_id,
            "title": title.strip(),
            "company": company.strip(),
            "location": location,
            "url": urllib.parse.urljoin("https://www.hellowork.com", href),
        })


def parse_hellowork_offers(markup):
    parser = HelloworkOfferParser()
    parser.feed(markup or "")
    return parser.offers


def scan_hellowork(conn, silent_init, session):
    processed = 0
    seen_ids = set()
    for query in HELLOWORK_QUERIES:
        previous_page_ids = None
        for page in range(1, HELLOWORK_MAX_PAGES + 1):
            data = request_text(
                session, "GET",
                "https://www.hellowork.com/fr-fr/emploi/recherche.html",
                f"HelloWork/{query}/page-{page}",
                params={"k": query, "l": HELLOWORK_LOCATION, "p": page},
            )
            if data is None:
                break
            offers = parse_hellowork_offers(data)
            if not offers:
                if page == 1:
                    print(f"[AVERTISSEMENT] HelloWork ne renvoie aucune offre pour {query!r}.")
                break
            page_ids = {offer["id"] for offer in offers}
            if page_ids == previous_page_ids:
                break
            previous_page_ids = page_ids
            for offer in offers:
                if offer["id"] in seen_ids:
                    continue
                seen_ids.add(offer["id"])
                # La recherche est explicitement limitée à la France ; le lieu
                # d'une carte HelloWork n'inclut généralement que la ville et le
                # département, pas le pays.
                location = f"{offer['location']}, France"
                processed += process_job(
                    conn, f"hw_{offer['id']}", offer["company"], offer["title"],
                    location, offer["url"], "HelloWork", silent_init, session,
                )
    return processed


def parse_wttj_env(payload):
    """Reads the rotating public Algolia credentials from /api/env."""
    start = payload.find("{")
    end = payload.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("/api/env ne contient pas d'objet JSON")
    try:
        environment = json.loads(payload[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("/api/env ne contient pas un JSON valide") from exc
    app_id = str(environment.get("PUBLIC_ALGOLIA_APPLICATION_ID", "")).strip()
    api_key = str(environment.get("PUBLIC_ALGOLIA_API_KEY_CLIENT", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9]{6,16}", app_id):
        raise ValueError("identifiant Algolia inattendu")
    if not 16 <= len(api_key) <= 500:
        raise ValueError("clé Algolia inattendue")
    return app_id, api_key


def normalize_wttj_hit(hit):
    if not isinstance(hit, dict):
        return None
    title = str(hit.get("name", "")).strip()
    organization = hit.get("organization") or {}
    company = str(organization.get("name", "Welcome to the Jungle")).strip()
    slug = str(hit.get("slug", "")).strip()
    organization_slug = str(organization.get("slug", "")).strip()
    if not title or not slug or not organization_slug:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", slug) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", organization_slug
    ):
        return None
    office = (hit.get("offices") or [None])[0] or {}
    location_parts = [
        str(office.get("city", "")).strip(),
        str(office.get("country", "")).strip(),
    ]
    location_parts = [part for part in location_parts if part]
    if hit.get("remote") == "fulltime":
        location_parts.append("Remote")
    location = ", ".join(location_parts) or "France"
    return {
        "id": str(hit.get("objectID") or hit.get("id") or
                  f"{organization_slug}/{slug}"),
        "title": title,
        "company": company or "Welcome to the Jungle",
        "location": location,
        "url": f"{WTTJ_SITE_ORIGIN}/fr/companies/{organization_slug}/jobs/{slug}",
        "description": str(hit.get("description", "")),
    }


def scan_welcome_to_jungle(conn, silent_init, session):
    if not WTTJ_QUERIES:
        print("[AVERTISSEMENT] WTTJ_QUERIES est vide.")
        return 0
    app_id, api_key = WTTJ_ALGOLIA_APP_ID, WTTJ_ALGOLIA_API_KEY
    if not app_id or not api_key:
        payload = request_text(
            session, "GET", WTTJ_ENV_URL, "WelcomeToTheJungle/env",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "application/javascript, text/javascript, */*",
                "Referer": f"{WTTJ_SITE_ORIGIN}/",
                "Origin": WTTJ_SITE_ORIGIN,
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            },
        )
        if payload is None:
            return 0
        try:
            app_id, api_key = parse_wttj_env(payload)
        except ValueError as exc:
            print(f"[ERREUR WTTJ] {exc}")
            return 0

    processed = 0
    seen_ids = set()
    algolia_url = f"https://{app_id}-dsn.algolia.net/1/indexes/{WTTJ_INDEX}/query"
    headers = {
        "x-algolia-application-id": app_id,
        "x-algolia-api-key": api_key,
        "Referer": f"{WTTJ_SITE_ORIGIN}/",
        "Content-Type": "application/json",
    }
    for query in WTTJ_QUERIES:
        params = {
            "query": query,
            "hitsPerPage": WTTJ_MAX_HITS,
            "attributesToRetrieve": (
                "name,slug,organization,offices,remote,description,objectID"
            ),
        }
        if WTTJ_FILTERS:
            params["filters"] = WTTJ_FILTERS
        data = request_json(
            session, "POST", algolia_url, f"WelcomeToTheJungle/{query}",
            headers=headers, json={"params": urllib.parse.urlencode(params)},
        )
        if not data:
            continue
        for hit in data.get("hits", []):
            offer = normalize_wttj_hit(hit)
            if not offer or offer["id"] in seen_ids:
                continue
            seen_ids.add(offer["id"])
            if (
                "country_code:FR" in WTTJ_FILTERS
                and not re.search(r"\b(?:france|fr)\b", offer["location"], re.IGNORECASE)
            ):
                offer["location"] += ", France"
            processed += process_job(
                conn, f"wttj_{offer['id']}", offer["company"], offer["title"],
                offer["location"], offer["url"], "Welcome to the Jungle",
                silent_init, session, offer["description"],
            )
    return processed


def scan_smartrecruiters(conn, silent_init, session):
    processed = 0
    for company, slug in SMARTRECRUITERS_COMPANIES:
        offset = 0
        while True:
            data = request_json(
                session, "GET",
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                f"SmartRecruiters/{company}",
                params={"limit": 100, "offset": offset},
            )
            if data is None:
                break
            jobs = data.get("content", [])
            for job in jobs:
                location = job.get("location") or {}
                location_text = location.get("fullLocation") or (
                    f"{location.get('city', '')}, {location.get('country', '')}"
                )
                experience = job.get("experienceLevel") or {}
                processed += process_job(
                    conn, f"sr_{job.get('id')}", company, job.get("name", ""),
                    location_text,
                    f"https://jobs.smartrecruiters.com/{slug}/{job.get('id')}",
                    "SmartRecruiters", silent_init, session,
                    experience_level=(
                        f"{experience.get('id', '')} {experience.get('label', '')}"
                    ),
                )
            offset += len(jobs)
            if not jobs or offset >= data.get("totalFound", offset):
                break
    return processed


def scan_lever(conn, silent_init, session):
    processed = 0
    for company, slug in LEVER_COMPANIES:
        jobs = request_json(
            session, "GET", f"https://api.lever.co/v0/postings/{slug}",
            f"Lever/{company}", params={"mode": "json"},
        )
        if jobs is None:
            continue
        for job in jobs:
            categories = job.get("categories") or {}
            processed += process_job(
                conn, f"lever_{job.get('id')}", company, job.get("text", ""),
                categories.get("location", ""), job.get("hostedUrl", ""),
                "Lever", silent_init, session,
                " ".join((job.get("descriptionPlain", ""),
                          job.get("additionalPlain", ""))),
            )
    return processed


def scan_greenhouse(conn, silent_init, session):
    processed = 0
    for company, slug in GREENHOUSE_COMPANIES:
        data = request_json(
            session, "GET",
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            f"Greenhouse/{company}", params={"content": "true"},
        )
        if data is None:
            continue
        for job in data.get("jobs", []):
            description = re.sub(
                r"<[^>]+>", " ", html.unescape(job.get("content", ""))
            )
            processed += process_job(
                conn, f"gh_{job.get('id')}", company, job.get("title", ""),
                (job.get("location") or {}).get("name", ""),
                job.get("absolute_url", ""), "Greenhouse", silent_init, session,
                description,
            )
    return processed


def scan_ashby(conn, silent_init, session):
    processed = 0
    for company, slug in ASHBY_COMPANIES:
        data = request_json(
            session, "GET",
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            f"Ashby/{company}",
        )
        if data is None:
            continue
        for job in data.get("jobs", []):
            processed += process_job(
                conn, f"ashby_{job.get('id')}", company, job.get("title", ""),
                job.get("location", ""), job.get("jobUrl", ""), "Ashby",
                silent_init, session, job.get("descriptionPlain", ""),
            )
    return processed


def scan_workday(conn, silent_init, session):
    processed = 0
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    for company in WORKDAY_COMPANIES:
        seen_paths = set()
        previous_signature = None
        expected_total = None
        # Une lecture exhaustive est plus fiable et moins couteuse que trois
        # recherches dont certains tenants Workday ignorent le texte.
        for page in range(WORKDAY_MAX_PAGES):
            data = request_json(
                session, "POST", company["url"],
                f"Workday/{company['name']}/page-{page + 1}",
                json={"appliedFacets": {}, "limit": 20, "offset": page * 20,
                      "searchText": ""},
                headers=headers,
            )
            if data is None:
                break
            jobs = data.get("jobPostings", [])
            signature = tuple(job.get("externalPath") for job in jobs)
            if not jobs or signature == previous_signature:
                break
            previous_signature = signature
            for job in jobs:
                external_path = job.get("externalPath", "")
                if not external_path or external_path in seen_paths:
                    continue
                seen_paths.add(external_path)
                processed += process_job(
                    conn, f"wd_{company['name']}_{external_path}",
                    company["name"], job.get("title", ""),
                    job.get("locationsText", ""),
                    f"{company['base_link']}{external_path}", "Workday",
                    silent_init, session,
                )
            total = data.get("total")
            if isinstance(total, int) and total > 0:
                expected_total = total
            if (len(jobs) < 20 or
                    (expected_total is not None and
                     (page + 1) * 20 >= expected_total)):
                break
        else:
            print(
                f"[AVERTISSEMENT] Limite de {WORKDAY_MAX_PAGES} pages "
                f"atteinte pour Workday/{company['name']}."
            )
    return processed


def provider_scanners():
    return {
        "SmartRecruiters": scan_smartrecruiters,
        "Lever": scan_lever,
        "Greenhouse": scan_greenhouse,
        "Ashby": scan_ashby,
        "Workday": scan_workday,
        "HelloWork": scan_hellowork,
        "WelcomeToTheJungle": scan_welcome_to_jungle,
    }


def run_provider_worker(provider_name, silent_init):
    """Run one provider in a separately killable process.

    The worker owns the SQLite connection and notification session. The parent
    only reopens the database after the worker exits, so a killed worker cannot
    leave the parent holding a stale SQLite connection.
    """
    scanner = provider_scanners().get(provider_name)
    if scanner is None:
        raise ValueError(f"Unknown provider: {provider_name}")
    conn, _ = init_db()
    session = create_ingestion_session()
    try:
        processed = scanner(conn, silent_init, session)
        print(
            "[ATS_PROVIDER_RESULT] "
            + json.dumps({"provider": provider_name, "processed": processed}),
            flush=True,
        )
        return 1 if SCAN_HAD_FAILURES else 0
    finally:
        session.close()
        conn.close()


def terminate_provider_process(process):
    """Terminate the worker and any descendants without an unbounded wait."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            process.kill()


def run_provider_isolated(provider_name, silent_init, deadline):
    """Run a provider with a hard wall-clock deadline and terminate on timeout."""
    global SCAN_HAD_FAILURES
    if time.monotonic() >= deadline:
        SCAN_HAD_FAILURES = True
        log_event("provider_skipped_scan_deadline", provider=provider_name)
        return 0
    started = time.monotonic()
    log_event("provider_start", provider=provider_name, timeout_seconds=PROVIDER_TIMEOUT_SECONDS)
    command = [sys.executable, str(Path(__file__).resolve()), "--provider-worker", provider_name]
    if silent_init:
        command.append("--silent-init")
    child_env = os.environ.copy()
    child_env["ATS_DB_FILE"] = DB_FILE
    remaining = max(1, int(deadline - time.monotonic()))
    timeout = min(PROVIDER_TIMEOUT_SECONDS, remaining)
    output = ""
    timed_out = False
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent),
                env=child_env,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
                start_new_session=(os.name != "nt"),
            )
        except OSError as exc:
            SCAN_HAD_FAILURES = True
            log_event(
                "provider_start_failed", provider=provider_name,
                error_type=type(exc).__name__, error=str(exc)[:200],
            )
            return 0
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_provider_process(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        output_file.seek(0)
        output = output_file.read()
    if output:
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if timed_out:
        SCAN_HAD_FAILURES = True
        log_event(
            "provider_timeout", provider=provider_name,
            elapsed_ms=elapsed_ms, timeout_seconds=timeout,
        )
        return 0
    if process.returncode != 0:
        SCAN_HAD_FAILURES = True
        log_event(
            "provider_failed", provider=provider_name,
            elapsed_ms=elapsed_ms, exit_code=process.returncode,
        )
        return 0
    match = re.findall(r"\[ATS_PROVIDER_RESULT\] (\{.*\})", output)
    processed = 0
    if match:
        try:
            processed = int(json.loads(match[-1]).get("processed", 0))
        except (TypeError, ValueError, json.JSONDecodeError):
            processed = 0
    log_event(
        "provider_complete", provider=provider_name,
        elapsed_ms=elapsed_ms, processed=processed,
    )
    return processed


def validate_web_only_config():
    if not ingestion_enabled():
        raise RuntimeError(
            "Web-only mode requires ATS_INGESTION_API_URL and "
            "ATS_INGESTION_SHARED_SECRET."
        )
    host = urllib.parse.urlparse(INGESTION_API_URL).hostname
    local_hosts = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
    allowed_remote_host = os.getenv("ATS_WEB_ONLY_ALLOWED_HOST", "").strip().lower()
    if host not in local_hosts and host != allowed_remote_host:
        raise RuntimeError(
            "Web-only mode only accepts localhost or the explicitly configured "
            "ATS_WEB_ONLY_ALLOWED_HOST."
        )
    if DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Web-only mode refuses to start while Discord or Telegram credentials are set."
        )


def web_only_db_file():
    path = Path(os.getenv("ATS_WEB_ONLY_DB_FILE", "local_jobs_seen.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def run_single_scan(db_file=None, web_only=False):
    global DB_FILE, WEB_ONLY_MODE, WEB_ONLY_DETAIL_CACHE, WEB_ONLY_DETAIL_STATS, WEB_ONLY_DETAIL_REQUESTS, WEB_ONLY_DETAIL_REQUESTS_NEW, WEB_ONLY_DETAIL_REQUESTS_EXISTING, WEB_ONLY_ACCEPTED_JOBS, WEB_ONLY_DETAIL_LAST_ERROR, SCAN_HAD_FAILURES
    previous_db_file = DB_FILE
    previous_web_only = WEB_ONLY_MODE
    previous_detail_cache = WEB_ONLY_DETAIL_CACHE
    previous_detail_stats = WEB_ONLY_DETAIL_STATS
    previous_detail_requests = WEB_ONLY_DETAIL_REQUESTS
    previous_detail_requests_new = WEB_ONLY_DETAIL_REQUESTS_NEW
    previous_detail_requests_existing = WEB_ONLY_DETAIL_REQUESTS_EXISTING
    previous_accepted_jobs = WEB_ONLY_ACCEPTED_JOBS
    previous_detail_errors = WEB_ONLY_DETAIL_LAST_ERROR
    if db_file:
        DB_FILE = db_file
    WEB_ONLY_MODE = web_only
    WEB_ONLY_DETAIL_CACHE = {}
    WEB_ONLY_DETAIL_STATS = {}
    WEB_ONLY_DETAIL_REQUESTS = 0
    WEB_ONLY_DETAIL_REQUESTS_NEW = 0
    WEB_ONLY_DETAIL_REQUESTS_EXISTING = 0
    WEB_ONLY_ACCEPTED_JOBS = 0
    WEB_ONLY_DETAIL_LAST_ERROR = {}
    SCAN_HAD_FAILURES = False
    conn, is_first_run = init_db()
    conn.close()
    session = create_http_session()
    ingested = 0
    processed = 0
    scan_deadline = time.monotonic() + SCAN_TIMEOUT_SECONDS
    if is_first_run:
        print("Initialisation: les offres deja presentes seront enregistrees sans alerte.")
    try:
        for provider_name in provider_scanners():
            found = run_provider_isolated(provider_name, is_first_run, scan_deadline)
            processed += found
            conn, _ = init_db()
            try:
                provider_ingested = flush_ingestion_queue(
                    conn, session, deadline=scan_deadline
                )
                ingested += provider_ingested
                log_event(
                    "provider_ingestion_flush", provider=provider_name,
                    delivered=provider_ingested,
                )
                if web_only:
                    print(f"[WEB ONLY] {provider_name}: {found} nouvelle(s) offre(s).")
            finally:
                conn.close()
            if time.monotonic() >= scan_deadline:
                log_event("scan_deadline_reached", processed=processed)
                break
        if web_only:
            conn, _ = init_db()
            pending = conn.execute(
                "SELECT COUNT(*) FROM supabase_ingestion_queue WHERE status = 'pending'"
            ).fetchone()[0]
            conn.close()
            print(
                f"[WEB ONLY] discovered={processed} delivered={ingested} "
                f"pending={pending} notifications=disabled "
                f"accepted={WEB_ONLY_ACCEPTED_JOBS} details={json.dumps(WEB_ONLY_DETAIL_STATS, sort_keys=True)}"
            )
    finally:
        session.close()
        DB_FILE = previous_db_file
        WEB_ONLY_MODE = previous_web_only
        WEB_ONLY_DETAIL_CACHE = previous_detail_cache
        WEB_ONLY_DETAIL_STATS = previous_detail_stats
        WEB_ONLY_DETAIL_REQUESTS = previous_detail_requests
        WEB_ONLY_DETAIL_REQUESTS_NEW = previous_detail_requests_new
        WEB_ONLY_DETAIL_REQUESTS_EXISTING = previous_detail_requests_existing
        WEB_ONLY_ACCEPTED_JOBS = previous_accepted_jobs
        WEB_ONLY_DETAIL_LAST_ERROR = previous_detail_errors
    print(f"[COUVERTURE NON DISPONIBLE] {', '.join(UNSUPPORTED_COMPANIES)}")
    print(
        f"[{datetime.now().astimezone().strftime('%H:%M:%S')}] "
        f"Scan termine: {processed} offre(s) nouvelle(s) traitee(s)."
    )
    if ingestion_enabled():
        print(f"[SUPABASE] {ingested} offre(s) envoyee(s), file locale independante active.")


if __name__ == "__main__":
    if "--provider-worker" in sys.argv:
        try:
            provider_index = sys.argv.index("--provider-worker") + 1
            provider_name = sys.argv[provider_index]
            raise_code = run_provider_worker(
                provider_name, "--silent-init" in sys.argv
            )
        except (IndexError, ValueError) as exc:
            print(f"[ATS_PROVIDER_WORKER][ERREUR] {exc}", flush=True)
            raise SystemExit(2)
        raise SystemExit(raise_code)
    elif "--web-only" in sys.argv:
        try:
            validate_web_only_config()
            local_db = web_only_db_file()
        except RuntimeError as exc:
            print(f"[WEB ONLY][ERREUR CONFIG] {exc}")
            raise SystemExit(2)
        if "--loop" in sys.argv:
            print(
                f"Mode web-only continu active (scan toutes les "
                f"{SCAN_INTERVAL_SECONDS // 60} minutes)."
            )
            try:
                while True:
                    run_single_scan(local_db, web_only=True)
                    time.sleep(SCAN_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                print("[WEB ONLY] Arret demande par l'utilisateur.")
        else:
            run_single_scan(local_db, web_only=True)
    elif "--loop" in sys.argv:
        print(f"Mode continu active (scan toutes les {SCAN_INTERVAL_SECONDS // 60} minutes).")
        while True:
            run_single_scan()
            time.sleep(SCAN_INTERVAL_SECONDS)
    else:
        run_single_scan()
    if SCAN_HAD_FAILURES:
        raise SystemExit(1)
