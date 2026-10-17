import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import datetime
import requests

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================

# Récupère l'URL du Webhook depuis les variables d'environnement (GitHub Actions) ou en dur en local
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_FILE = "jobs_seen.db"

# ==========================================
# 2. FILTRES CIBLÉS (JUNIOR DATA / AI / ML)
# ==========================================

# Ciblage : Data Scientist, Data Engineer, Data Analyst, AI Engineer, ML Engineer
POSITIVE_KEYWORDS = [
    r"data scientist", r"data science",
    r"data engineer", r"ingénieur data", r"ingenieur data", r"analytics engineer",
    r"data analyst", r"business data analyst",
    r"ai engineer", r"ingénieur ia", r"ingenieur ia", r"artificial intelligence", r"genai", r"llm",
    r"ml engineer", r"machine learning", r"mlops", r"deep learning"
]

# Exclusion stricte : Stages, Alternances et profils Seniors/Management
NEGATIVE_KEYWORDS = [
    r"\bstage\b", r"stagiaire", r"\bintern\b", r"internship",
    r"alternance", r"alternant", r"apprentissage", r"apprenti",
    r"senior", r"sénior", r"\blead\b", r"principal", r"\bstaff\b",
    r"manager", r"directeur", r"director", r"head of", r"\bvp\b", r"chef de"
]

# Localisations ciblées (France / Île-de-France)
LOCATIONS = [
    r"paris", r"france", r"île-de-france", r"ile-de-france", r"la défense",
    r"puteaux", r"courbevoie", r"montrouge", r"massy", r"saint-denis",
    r"issy", r"boulogne", r"levallois", r"neuilly", r"châtillon", r"ivry"
]

# ==========================================
# 3. ENTREPRISES CIBLES PAR MOTEUR ATS
# ==========================================

# SmartRecruiters (Banques, ESN, Grands Groupes)
SMARTRECRUITERS_COMPANIES = [
    "Natixis",           # BPCE / Natixis
    "Devoteam",          # ESN Data / IA
    "PublicisGroupe",    # Epsilon / Publicis Data
    "Equativ",           # AdTech
    "Criteo",            # AI / ML / Data
]

# Lever (Conseil, Licornes Tech, IA)
LEVER_COMPANIES = [
    "sia-partners",      # Conseil Data / IA / Banque
    "mistral",           # Mistral AI
    "qonto",             # Fintech
    "payfit",            # Tech
    "spendesk",          # Fintech
    "manomano",          # E-commerce Data
]

# Greenhouse (Pure Players Data, IA, Tech)
GREENHOUSE_COMPANIES = [
    "artefact",          # Conseil Data & AI pur
    "doctolib",          # HealthTech
    "contentsquare",     # Data / AI
    "datadog",           # Tech
    "alan",              # AssurTech
    "backmarket",        # Tech
    "blablacar",         # Tech
    "huggingface",       # AI / ML
]

# Workday (Grands Groupes, Banques, Assurances, ESN)
WORKDAY_COMPANIES = [
    {
        "name": "AXA",
        "url": "https://axa.wd3.myworkdayjobs.com/wday/cxs/axa/AXA_External_Career_Site/jobs",
        "base_link": "https://axa.wd3.myworkdayjobs.com/fr-FR/AXA_External_Career_Site"
    },
    {
        "name": "Capgemini",
        "url": "https://capgemini.wd3.myworkdayjobs.com/wday/cxs/capgemini/Capgemini_Careers/jobs",
        "base_link": "https://capgemini.wd3.myworkdayjobs.com/fr-FR/Capgemini_Careers"
    },
    {
        "name": "Sanofi",
        "url": "https://sanofi.wd3.myworkdayjobs.com/wday/cxs/sanofi/SanofiCareers/jobs",
        "base_link": "https://sanofi.wd3.myworkdayjobs.com/fr-FR/SanofiCareers"
    },
    {
        "name": "Thales",
        "url": "https://thales.wd3.myworkdayjobs.com/wday/cxs/thales/Careers/jobs",
        "base_link": "https://thales.wd3.myworkdayjobs.com/fr-FR/Careers"
    }
]

# ==========================================
# 4. GESTION SQLITE & DÉDOUBLONNAGE
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            company TEXT,
            title TEXT,
            url TEXT,
            detected_at TIMESTAMP
        )
    """)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM seen_jobs")
    count = cursor.fetchone()[0]
    return conn, (count == 0)

def register_job(conn, job_id, company, title, url):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,))
    if cursor.fetchone():
        return False
    cursor.execute(
        "INSERT INTO seen_jobs (job_id, company, title, url, detected_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, company, title, url, datetime.now().isoformat())
    )
    conn.commit()
    return True

# ==========================================
# 5. FILTRAGE & ENVOI DES NOTIFICATIONS
# ==========================================

def matches_criteria(title, location):
    title_low = (title or "").lower()
    loc_low = (location or "").lower()

    if not any(re.search(loc, loc_low) for loc in LOCATIONS):
        return False
    if any(re.search(neg, title_low) for neg in NEGATIVE_KEYWORDS):
        return False
    if any(re.search(pos, title_low) for pos in POSITIVE_KEYWORDS):
        return True
    return False

def build_xray_links(company):
    comp_clean = company.replace("-", " ").upper()
    mgr_query = f'site:fr.linkedin.com/in/ "{comp_clean}" ("Head of Data" OR "Lead Data" OR "Manager Data" OR "Head of AI" OR "Data Science Manager")'
    rec_query = f'site:fr.linkedin.com/in/ "{comp_clean}" ("Talent Acquisition" OR "Recruteur" OR "Recruiter") ("Data" OR "Tech" OR "IT")'
    
    mgr_url = f"https://www.google.com/search?q={urllib.parse.quote(mgr_query)}"
    rec_url = f"https://www.google.com/search?q={urllib.parse.quote(rec_query)}"
    return mgr_url, rec_url

def send_alert(company, title, location, url, ats_source, silent_init=False):
    if silent_init:
        print(f"[INIT SILENCIEUX] Enregistré : {company} - {title}")
        return

    mgr_url, rec_url = build_xray_links(company)
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")

    msg = (
        f"🚨 **NOUVELLE OFFRE DATA/IA ({ats_source})** 🚨\n"
        f"🏢 **Entreprise :** {company}\n"
        f"💼 **Poste :** {title}\n"
        f"📍 **Lieu :** {location}\n"
        f"⚡ **Postuler en 1er :** {url}\n\n"
        f"🎯 **[Chasser le Manager Data sur LinkedIn]({mgr_url})**\n"
        f"🕵️ **[Chasser le Recruteur Tech sur LinkedIn]({rec_url})**\n"
        f"⏱️ *Détectée le {now_str}*"
    )

    print("\n" + "=" * 55)
    print(msg)
    print("=" * 55)

    # 1. Envoi Discord
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=10)
        except Exception as e:
            print(f"[Erreur Discord] {e}")

    # 2. Envoi Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            requests.post(tg_url, json=payload, timeout=10)
        except Exception as e:
            print(f"[Erreur Telegram] {e}")

# ==========================================
# 6. CONNECTEURS API ATS
# ==========================================

def scan_smartrecruiters(conn, silent_init):
    for company in SMARTRECRUITERS_COMPANIES:
        url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                for job in r.json().get("content", []):
                    job_id = f"sr_{job['id']}"
                    title = job.get("name", "")
                    loc_obj = job.get("location", {})
                    loc = f"{loc_obj.get('city', '')}, {loc_obj.get('country', '')}"
                    job_url = f"https://jobs.smartrecruiters.com/{company}/{job['id']}"

                    if matches_criteria(title, loc):
                        if register_job(conn, job_id, company, title, job_url):
                            send_alert(company, title, loc, job_url, "SmartRecruiters", silent_init)
        except Exception as e:
            print(f"[Erreur SmartRecruiters - {company}] {e}")

def scan_lever(conn, silent_init):
    for company in LEVER_COMPANIES:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                for job in r.json():
                    job_id = f"lever_{job['id']}"
                    title = job.get("text", "")
                    loc = job.get("categories", {}).get("location", "")
                    job_url = job.get("hostedUrl", "")

                    if matches_criteria(title, loc):
                        if register_job(conn, job_id, company.upper(), title, job_url):
                            send_alert(company.upper(), title, loc, job_url, "Lever", silent_init)
        except Exception as e:
            print(f"[Erreur Lever - {company}] {e}")

def scan_greenhouse(conn, silent_init):
    for company in GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                for job in r.json().get("jobs", []):
                    job_id = f"gh_{job['id']}"
                    title = job.get("title", "")
                    loc = job.get("location", {}).get("name", "")
                    job_url = job.get("absolute_url", "")

                    if matches_criteria(title, loc):
                        if register_job(conn, job_id, company.upper(), title, job_url):
                            send_alert(company.upper(), title, loc, job_url, "Greenhouse", silent_init)
        except Exception as e:
            print(f"[Erreur Greenhouse - {company}] {e}")

def scan_workday(conn, silent_init):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    # On cherche large avec "Data" et "AI", puis notre regex affine sur les 5 métiers
    for search_term in ["Data", "AI", "Machine Learning"]:
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": search_term}
        for comp in WORKDAY_COMPANIES:
            try:
                r = requests.post(comp["url"], json=payload, headers=headers, timeout=15)
                if r.status_code == 200:
                    for job in r.json().get("jobPostings", []):
                        ext_path = job.get("externalPath", "")
                        job_id = f"wd_{comp['name']}_{ext_path}"
                        title = job.get("title", "")
                        loc = job.get("locationsText", "")
                        job_url = f"{comp['base_link']}{ext_path}"

                        if matches_criteria(title, loc):
                            if register_job(conn, job_id, comp["name"], title, job_url):
                                send_alert(comp["name"], title, loc, job_url, "Workday", silent_init)
            except Exception as e:
                print(f"[Erreur Workday - {comp['name']}] {e}")

def run_single_scan():
    conn, is_first_run = init_db()
    if is_first_run:
        print("Initialisation de la base SQLite : enregistrement silencieux des offres actuelles...")
    
    scan_smartrecruiters(conn, is_first_run)
    scan_lever(conn, is_first_run)
    scan_greenhouse(conn, is_first_run)
    scan_workday(conn, is_first_run)
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan terminé avec succès.")

if __name__ == "__main__":
    # Si on lance avec "--loop" sur son PC, il tourne en boucle toutes les 5 minutes
    if "--loop" in sys.argv:
        import time
        print("Mode continu activé (Scan toutes les 5 minutes)...")
        while True:
            run_single_scan()
            time.sleep(300)
    else:
        # Exécution unique (idéal pour le déclencheur GitHub Actions)
        run_single_scan()