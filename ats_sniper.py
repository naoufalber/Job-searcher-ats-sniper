import html
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser

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
WORKDAY_MAX_PAGES = int(os.getenv("WORKDAY_MAX_PAGES", "100"))
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


def request_json(session, method, url, source, **kwargs):
    try:
        response = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[ERREUR API] {source}: {exc}")
        return None


def request_text(session, method, url, source, **kwargs):
    try:
        response = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.text
    except (requests.RequestException, AttributeError) as exc:
        print(f"[ERREUR HTTP] {source}: {exc}")
        return None


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
    if not matches_criteria(title, location, description, experience_level):
        return 0
    if not queue_job(conn, job_id, company, title, url):
        return 0
    if silent_init:
        mark_job(conn, job_id, "baseline")
        print(f"[INITIALISATION] {company} - {title}")
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


def run_single_scan():
    conn, is_first_run = init_db()
    session = create_http_session()
    if is_first_run:
        print("Initialisation: les offres deja presentes seront enregistrees sans alerte.")
    try:
        processed = scan_smartrecruiters(conn, is_first_run, session)
        processed += scan_lever(conn, is_first_run, session)
        processed += scan_greenhouse(conn, is_first_run, session)
        processed += scan_ashby(conn, is_first_run, session)
        processed += scan_workday(conn, is_first_run, session)
        processed += scan_hellowork(conn, is_first_run, session)
        processed += scan_welcome_to_jungle(conn, is_first_run, session)
    finally:
        session.close()
        conn.close()
    print(f"[COUVERTURE NON DISPONIBLE] {', '.join(UNSUPPORTED_COMPANIES)}")
    print(
        f"[{datetime.now().astimezone().strftime('%H:%M:%S')}] "
        f"Scan termine: {processed} offre(s) nouvelle(s) traitee(s)."
    )


if __name__ == "__main__":
    if "--loop" in sys.argv:
        print(f"Mode continu active (scan toutes les {SCAN_INTERVAL_SECONDS // 60} minutes).")
        while True:
            run_single_scan()
            time.sleep(SCAN_INTERVAL_SECONDS)
    else:
        run_single_scan()
