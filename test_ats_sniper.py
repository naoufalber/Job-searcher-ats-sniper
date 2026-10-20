import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import ats_sniper as sniper


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

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
