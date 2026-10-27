import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import ats_sniper as sniper


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None):
        self.payload = payload
        self.status_code = status_code
        self.text = text if text is not None else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise sniper.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class PaginatedSmartRecruitersSession:
    def __init__(self):
        self.offsets = []

    def request(self, method, url, timeout, **kwargs):
        offset = kwargs["params"]["offset"]
        self.offsets.append(offset)
        jobs = {
            0: [{
                "id": "one",
                "name": "Data Engineer",
                "location": {"city": "Paris", "country": "fr"},
            }],
            1: [{
                "id": "two",
                "name": "Machine Learning Engineer",
                "location": {"city": "Lyon", "country": "fr"},
            }],
        }.get(offset, [])
        return FakeResponse({"content": jobs, "totalFound": 2})


class FilterTests(unittest.TestCase):
    def test_accepts_target_roles_in_france(self):
        cases = [
            ("Data Scientist Junior", "Paris"),
            ("Ingénieur Data", "Lyon, FR"),
            ("ML Engineer", "Remote - France"),
            ("AI Engineer", "Île de France"),
        ]
        for title, location in cases:
            with self.subTest(title=title):
                self.assertTrue(sniper.matches_criteria(title, location))

    def test_rejects_non_target_or_senior_roles(self):
        cases = [
            ("Senior Data Scientist", "Paris", ""),
            ("Data Engineer Expérimenté", "Paris", ""),
            ("Team Leader / Data & AI Engineer", "Paris", ""),
            ("People Data Analyst", "Paris", ""),
            ("Workday Integration & Analytics Engineer", "Paris", ""),
            ("Stage Data Analyst", "Paris", ""),
            ("Metadata Analyst", "Paris", ""),
            ("Data Engineer", "Berlin", ""),
            ("Data Engineer", "Paris", "Minimum 5 years of experience"),
        ]
        for title, location, description in cases:
            with self.subTest(title=title):
                self.assertFalse(sniper.matches_criteria(title, location, description))

    def test_rejects_senior_ats_experience_level(self):
        self.assertFalse(
            sniper.matches_criteria(
                "Data Engineer", "Paris, France", "", "mid_senior_level"
            )
        )


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "jobs.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migrates_legacy_database(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE seen_jobs (
                job_id TEXT PRIMARY KEY, company TEXT, title TEXT,
                url TEXT, detected_at TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO seen_jobs VALUES ('old', 'Test', 'Data Engineer', 'url', 'date')"
        )
        conn.commit()
        conn.close()

        with patch.object(sniper, "DB_FILE", self.db_path):
            migrated, first_run = sniper.init_db()
        try:
            self.assertFalse(first_run)
            status = migrated.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'old'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
        finally:
            migrated.close()

    def test_failed_notification_is_retried(self):
        with patch.object(sniper, "DB_FILE", self.db_path):
            conn, _ = sniper.init_db()
        try:
            args = (
                conn, "job-1", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job", "TestATS", False, object(),
            )
            with patch.object(sniper, "send_alert", return_value=False) as send:
                self.assertEqual(sniper.process_job(*args), 0)
                self.assertEqual(sniper.process_job(*args), 0)
                self.assertEqual(send.call_count, 2)
            status = conn.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-1'"
            ).fetchone()[0]
            self.assertEqual(status, "pending")

            with patch.object(sniper, "send_alert", return_value=True):
                self.assertEqual(sniper.process_job(*args), 1)
            status = conn.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-1'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
        finally:
            conn.close()


class NotificationTests(unittest.TestCase):
    def test_discord_success_is_reported(self):
        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, json, timeout):
                self.calls.append((url, json, timeout))
                return FakeResponse({})

        session = Session()
        with (
            patch.object(sniper, "DISCORD_WEBHOOK_URL", "https://discord.test/webhook"),
            patch.object(sniper, "TELEGRAM_BOT_TOKEN", ""),
            patch.object(sniper, "TELEGRAM_CHAT_ID", ""),
        ):
            delivered = sniper.send_alert(
                "Test", "Data Engineer", "Paris", "https://example.test/job",
                "TestATS", session,
            )
        self.assertTrue(delivered)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("Data Engineer", session.calls[0][1]["content"])


class JobBoardParserTests(unittest.TestCase):
    def test_parses_hellowork_server_rendered_card(self):
        markup = """
        <a data-cy="offerTitle" href="/fr-fr/emplois/123456.html"
           title="Data Engineer - Data Solutions H/F - Example Corp"
           aria-label="Voir offre de Data Engineer - Data Solutions H/F à Paris - 75, chez Example Corp, pour un CDI">
          <h3><span>Data Engineer - Data Solutions H/F</span></h3>
        </a>
        """
        offers = sniper.parse_hellowork_offers(markup)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["id"], "123456")
        self.assertEqual(offers[0]["company"], "Example Corp")
        self.assertEqual(offers[0]["title"], "Data Engineer - Data Solutions H/F")
        self.assertEqual(offers[0]["location"], "Paris - 75")

    def test_normalizes_welcome_to_the_jungle_hit(self):
        offer = sniper.normalize_wttj_hit({
            "objectID": "abc123",
            "name": "Data Architect",
            "slug": "data-architect_paris_abc123",
            "organization": {"name": "Example", "slug": "example"},
            "offices": [{"city": "Paris", "country": "France"}],
            "remote": "fulltime",
        })
        self.assertEqual(offer["id"], "abc123")
        self.assertIn("Paris", offer["location"])
        self.assertIn("Remote", offer["location"])
        self.assertIn("/fr/companies/example/jobs/", offer["url"])

    def test_parses_rotating_welcome_to_the_jungle_credentials(self):
        app_id, api_key = sniper.parse_wttj_env(
            'window.env = {"PUBLIC_ALGOLIA_APPLICATION_ID":"ABC12345",'
            '"PUBLIC_ALGOLIA_API_KEY_CLIENT":"0123456789abcdef0123"};'
        )
        self.assertEqual(app_id, "ABC12345")
        self.assertEqual(api_key, "0123456789abcdef0123")


class WelcomeToTheJungleScanTests(unittest.TestCase):
    def test_scans_public_algolia_results(self):
        class Session:
            def request(self, method, url, timeout, **kwargs):
                if url == sniper.WTTJ_ENV_URL:
                    return FakeResponse(
                        {}, text=(
                            'window.env = {"PUBLIC_ALGOLIA_APPLICATION_ID":"ABC12345",'
                            '"PUBLIC_ALGOLIA_API_KEY_CLIENT":"0123456789abcdef0123"};'
                        )
                    )
                return FakeResponse({
                    "hits": [{
                        "objectID": "job-1",
                        "name": "Data Engineer",
                        "slug": "data-engineer_paris_job-1",
                        "organization": {"name": "Example", "slug": "example"},
                        "offices": [{"city": "Paris"}],
                    }]
                })

        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "jobs.db")
            with patch.object(sniper, "DB_FILE", db_path):
                conn, _ = sniper.init_db()
            try:
                with patch.object(sniper, "WTTJ_ALGOLIA_APP_ID", ""), \
                     patch.object(sniper, "WTTJ_ALGOLIA_API_KEY", ""), \
                     patch.object(sniper, "WTTJ_QUERIES", ("data engineer",)), \
                     patch.object(sniper, "WTTJ_FILTERS", "country_code:FR"):
                    self.assertEqual(
                        sniper.scan_welcome_to_jungle(conn, True, Session()), 1
                    )
                row = conn.execute(
                    "SELECT company, title, notification_status FROM seen_jobs"
                ).fetchone()
                self.assertEqual(row, ("Example", "Data Engineer", "baseline"))
            finally:
                conn.close()


class PaginationTests(unittest.TestCase):
    def test_smartrecruiters_reads_every_page(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "jobs.db")
            with patch.object(sniper, "DB_FILE", db_path):
                conn, _ = sniper.init_db()
            session = PaginatedSmartRecruitersSession()
            try:
                with patch.object(
                    sniper, "SMARTRECRUITERS_COMPANIES", [("Test", "test")]
                ):
                    processed = sniper.scan_smartrecruiters(conn, True, session)
                self.assertEqual(processed, 2)
                self.assertEqual(session.offsets, [0, 1])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
