import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import ExitStack
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


class WebOnlyDetailTests(unittest.TestCase):
    def test_extracts_hellowork_entity_encoded_jsonld(self):
        fixture = Path(__file__).parent / "tests" / "fixtures" / "hellowork_job.html"
        detail = sniper.extract_hellowork_job_detail(fixture.read_text(encoding="utf-8"))
        self.assertEqual(detail["title"], "Data Engineer H/F")
        self.assertEqual(detail["company"], "Example Company")
        self.assertIn("pipelines de donnees", detail["description"])
        self.assertTrue(sniper.is_description_complete(detail["description"]))

    def test_web_only_fetches_missing_detail_before_ingestion(self):
        with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as patches:
            db_path = os.path.join(temp_dir, "local.db")
            patches.enter_context(patch.object(sniper, "DB_FILE", db_path))
            patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://127.0.0.1:3000"))
            patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
            patches.enter_context(patch.object(sniper, "WEB_ONLY_MODE", True))
            detail = patches.enter_context(patch.object(sniper, "fetch_web_only_description", return_value=(
                "Responsibilities include building data pipelines and models. "
                "Requirements include Python and SQL. Collaborate with stakeholders."
            )))
            conn, _ = sniper.init_db()
            try:
                with patch.object(sniper, "send_alert") as send:
                    self.assertEqual(sniper.process_job(
                        conn, "detail-1", "Example", "Data Engineer", "Paris, France",
                        "https://example.test/jobs/detail-1", "Greenhouse", False, object(),
                    ), 1)
                detail.assert_called_once()
                send.assert_not_called()
                payload = conn.execute(
                    "SELECT payload_json FROM supabase_ingestion_queue WHERE job_id = 'detail-1'"
                ).fetchone()[0]
                self.assertIn("Responsibilities", payload)
            finally:
                conn.close()

    def test_production_mode_does_not_fetch_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as patches:
            patches.enter_context(patch.object(sniper, "DB_FILE", os.path.join(temp_dir, "prod.db")))
            patches.enter_context(patch.object(sniper, "INGESTION_API_URL", ""))
            patches.enter_context(patch.object(sniper, "WEB_ONLY_MODE", False))
            conn, _ = sniper.init_db()
            try:
                with patch.object(sniper, "fetch_web_only_description") as detail, patch.object(sniper, "send_alert", return_value=True):
                    self.assertEqual(sniper.process_job(
                        conn, "detail-2", "Example", "Data Engineer", "Paris, France",
                        "https://example.test/jobs/detail-2", "Greenhouse", False, object(),
                    ), 1)
                detail.assert_not_called()
            finally:
                conn.close()

    def test_production_mode_revisits_existing_job_for_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as patches:
            patches.enter_context(patch.object(sniper, "DB_FILE", os.path.join(temp_dir, "existing.db")))
            patches.enter_context(patch.object(sniper, "INGESTION_API_URL", ""))
            patches.enter_context(patch.object(sniper, "WEB_ONLY_MODE", False))
            patches.enter_context(patch.object(sniper, "INGESTION_ENRICH_DETAILS", True))
            detail = patches.enter_context(patch.object(sniper, "fetch_web_only_description", return_value=(
                "Responsibilities include building data pipelines and models. "
                "Requirements include Python and SQL. Collaborate with stakeholders."
            )))
            conn, _ = sniper.init_db()
            try:
                conn.execute(
                    "INSERT INTO seen_jobs(job_id, company, title, url, detected_at, "
                    "notification_status) VALUES (?, ?, ?, ?, ?, ?)",
                    ("existing-detail", "Example", "Data Engineer", "https://example.test/existing", "now", "sent"),
                )
                conn.commit()
                with patch.object(sniper, "send_alert"):
                    self.assertEqual(sniper.process_job(
                        conn, "existing-detail", "Example", "Data Engineer", "Paris, France",
                        "https://example.test/existing", "HelloWork", False, object(),
                    ), 0)
                detail.assert_called_once()
            finally:
                conn.close()

    def test_blocked_hellowork_detail_does_not_block_notification(self):
        with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as patches:
            patches.enter_context(patch.object(sniper, "DB_FILE", os.path.join(temp_dir, "fallback.db")))
            patches.enter_context(patch.object(sniper, "INGESTION_API_URL", ""))
            patches.enter_context(patch.object(sniper, "WEB_ONLY_MODE", False))
            patches.enter_context(patch.object(sniper, "INGESTION_ENRICH_DETAILS", True))
            patches.enter_context(patch.object(sniper, "fetch_web_only_description", return_value=""))
            conn, _ = sniper.init_db()
            try:
                with patch.object(sniper, "send_alert", return_value=True) as alert:
                    result = sniper.process_job(
                        conn, "hellowork-fallback", "Example", "Data Engineer", "Paris, France",
                        "https://example.test/hellowork-fallback", "HelloWork", False, object(),
                    )
                self.assertEqual(result, 1)
                alert.assert_called_once()
            finally:
                conn.close()

    def test_web_only_retry_state_defers_repeated_failed_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as patches:
            patches.enter_context(patch.object(sniper, "DB_FILE", os.path.join(temp_dir, "retry.db")))
            patches.enter_context(patch.object(sniper, "INGESTION_API_URL", ""))
            patches.enter_context(patch.object(sniper, "WEB_ONLY_MODE", True))
            detail = patches.enter_context(patch.object(sniper, "fetch_web_only_description", return_value=""))
            conn, _ = sniper.init_db()
            try:
                args = (
                    conn, "retry-detail", "Example", "Data Engineer", "Paris, France",
                    "https://example.test/jobs/retry-detail", "HelloWork", False, object(),
                )
                sniper.process_job(*args)
                sniper.process_job(*args)
                detail.assert_called_once()
                row = conn.execute(
                    "SELECT status, attempts FROM web_only_enrichment WHERE job_id = 'retry-detail'"
                ).fetchone()
                self.assertEqual(row[0], "retry")
                self.assertEqual(row[1], 1)
            finally:
                conn.close()


class DatabaseTests(unittest.TestCase):
    def test_blocked_description_reason_is_ingested_and_notifications_continue(self):
        response = sniper.requests.Response()
        response.status_code = 403
        error = sniper.requests.HTTPError("Blocked", response=response)
        with patch.object(sniper, "DB_FILE", self.db_path), \
             patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"), \
             patch.object(sniper, "INGESTION_SHARED_SECRET", "test-secret"), \
             patch.object(sniper, "INGESTION_ENRICH_DETAILS", True), \
             patch.object(sniper, "WEB_ONLY_DETAIL_REQUESTS_NEW", 0), \
             patch.object(sniper, "WEB_ONLY_DETAIL_CACHE", {}), \
             patch.object(sniper, "WEB_ONLY_DETAIL_LAST_ERROR", {}), \
             patch.object(sniper, "send_alert", return_value=True) as alert:
            conn, _ = sniper.init_db()
            try:
                session = unittest.mock.Mock()
                session.request.side_effect = error
                sniper.process_job(conn,"blocked","Example","Data Engineer","Paris, France",
                    "https://www.hellowork.com/fr-fr/emplois/123.html","HelloWork",False,session)
                alert.assert_called_once()
                payload = conn.execute("SELECT payload_json FROM supabase_ingestion_queue").fetchone()[0]
                self.assertIn("HTTP 403", payload)
                self.assertEqual(conn.execute("SELECT notification_status FROM seen_jobs").fetchone()[0], "sent")
            finally:
                conn.close()

    def test_detail_budget_deferral_does_not_consume_retry_attempt(self):
        with patch.object(sniper, "DB_FILE", self.db_path), \
             patch.object(sniper, "WEB_ONLY_MODE", True), \
             patch.object(sniper, "WEB_ONLY_DETAIL_CACHE", {}), \
             patch.object(sniper, "WEB_ONLY_DETAIL_LAST_ERROR", {}), \
             patch.object(sniper, "WEB_ONLY_DETAIL_MAX_REQUESTS", 1), \
             patch.object(sniper, "WEB_ONLY_DETAIL_REQUESTS_NEW", 1):
            conn, _ = sniper.init_db()
            try:
                url = "https://jobs.smartrecruiters.com/Test/1"
                self.assertTrue(sniper.web_only_enrichment_due(conn, "budget", url))
                description = sniper.fetch_web_only_description("SmartRecruiters", url, object())
                sniper.record_web_only_enrichment(conn, "budget", url, description)
                self.assertEqual(conn.execute("SELECT status, attempts FROM web_only_enrichment").fetchone(), ("retry", 0))
                conn.execute("UPDATE web_only_enrichment SET adapter_revision = 1, status = 'terminal', attempts = 4")
                conn.commit()
                self.assertTrue(sniper.web_only_enrichment_due(conn, "budget", url))
                self.assertEqual(conn.execute("SELECT adapter_revision, attempts FROM web_only_enrichment").fetchone(), (2, 0))
            finally:
                conn.close()

    def test_new_ingestion_precedes_sent_job_enrichment_backlog(self):
        with patch.object(sniper, "DB_FILE", self.db_path), \
             patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"), \
             patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"), \
             patch.object(sniper, "INGESTION_BATCH_SIZE", 1):
            conn, _ = sniper.init_db()
            try:
                for job_id in ("old-enrichment", "new-vacancy"):
                    sniper.queue_ingestion(conn, sniper.build_ingestion_payload(job_id, "Test", "Data Engineer", "Paris", "https://example.test/job", "TestATS"))
                conn.execute("UPDATE supabase_ingestion_queue SET sent_at = '2020-01-01' WHERE job_id = 'old-enrichment'")
                conn.commit()
                session = unittest.mock.Mock()
                session.post.return_value = FakeResponse({})
                self.assertEqual(sniper.flush_ingestion_queue(conn, session), 1)
                self.assertEqual(session.post.call_args.kwargs["json"]["external_job_id"], "new-vacancy")
            finally:
                conn.close()

    def test_permanently_hanging_provider_is_terminated(self):
        real_popen = sniper.subprocess.Popen
        children = []

        def sleeping_provider(command, **kwargs):
            child = real_popen([sniper.sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
            children.append(child)
            return child

        with patch.object(sniper, "PROVIDER_TIMEOUT_SECONDS", 0.2), \
             patch.object(sniper, "SCAN_HAD_FAILURES", False), \
             patch.object(sniper.subprocess, "Popen", side_effect=sleeping_provider):
            # taskkill also uses Popen on Windows; restore the actual constructor
            # during cleanup so only the owned provider process is terminated.
            terminate = sniper.terminate_provider_process

            def terminate_child(child):
                with patch.object(sniper.subprocess, "Popen", real_popen):
                    terminate(child)

            started = time.monotonic()
            with patch.object(sniper, "terminate_provider_process", side_effect=terminate_child):
                self.assertEqual(sniper.run_provider_isolated("HelloWork", False, started + 5), 0)
            self.assertTrue(sniper.SCAN_HAD_FAILURES)
            self.assertLess(time.monotonic() - started, 5)
            self.assertIsNotNone(children[0].poll())

    def test_smartrecruiters_dictionary_sections_are_preserved(self):
        with patch.object(sniper, "INGESTION_ENRICH_DETAILS", True), \
             patch.object(sniper, "WEB_ONLY_DETAIL_CACHE", {}), \
             patch.object(sniper, "WEB_ONLY_DETAIL_REQUESTS_NEW", 0), \
             patch.object(sniper, "request_json", return_value={"jobAd": {"sections": {
                 "jobDescription": {"content": "<p>Responsibilities: develop Python services.</p>"},
                 "qualifications": {"content": "<p>Requirements: Python and SQL.</p>"},
             }}}):
            result = sniper.fetch_web_only_description("SmartRecruiters", "https://jobs.smartrecruiters.com/Example/123", object())
            self.assertIn("Responsibilities", result)
            self.assertIn("Requirements", result)

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

    def test_supabase_ingestion_failure_does_not_change_notification_state(self):
        patches = ExitStack()
        patches.enter_context(patch.object(sniper, "DB_FILE", self.db_path))
        patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"))
        patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
        conn, _ = sniper.init_db()
        try:
            args = (
                conn, "job-queue-1", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job", "TestATS", False, object(),
            )
            with patch.object(sniper, "send_alert", return_value=True), \
                 patch.object(sniper, "flush_ingestion_queue", return_value=0):
                self.assertEqual(sniper.process_job(*args), 1)
            status = conn.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-queue-1'"
            ).fetchone()[0]
            queue_status = conn.execute(
                "SELECT status FROM supabase_ingestion_queue WHERE job_id = 'job-queue-1'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
            self.assertEqual(queue_status, "pending")
        finally:
            conn.close()
            patches.close()

    def test_supabase_ingestion_queue_retries_independently(self):
        class Session:
            def __init__(self):
                self.fail = True
                self.calls = 0

            def post(self, url, **kwargs):
                self.calls += 1
                if self.fail:
                    raise sniper.requests.Timeout("temporary outage")
                return FakeResponse({})

        patches = ExitStack()
        patches.enter_context(patch.object(sniper, "DB_FILE", self.db_path))
        patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"))
        patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
        conn, _ = sniper.init_db()
        try:
            payload = sniper.build_ingestion_payload(
                "job-queue-2", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job-2", "TestATS",
            )
            sniper.queue_ingestion(conn, payload)
            session = Session()
            self.assertEqual(sniper.flush_ingestion_queue(conn, session), 0)
            row = conn.execute(
                "SELECT status, attempts FROM supabase_ingestion_queue WHERE job_id = 'job-queue-2'"
            ).fetchone()
            self.assertEqual(row, ("pending", 1))
            conn.execute("UPDATE supabase_ingestion_queue SET next_attempt_at = NULL")
            conn.commit()
            session.fail = False
            self.assertEqual(sniper.flush_ingestion_queue(conn, session), 1)
            status = conn.execute(
                "SELECT status FROM supabase_ingestion_queue WHERE job_id = 'job-queue-2'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
        finally:
            conn.close()
            patches.close()

    def test_ingestion_queue_write_failure_does_not_block_discord(self):
        patches = ExitStack()
        patches.enter_context(patch.object(sniper, "DB_FILE", self.db_path))
        patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"))
        patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
        conn, _ = sniper.init_db()
        try:
            args = (
                conn, "job-queue-write", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job-write", "TestATS", False, object(),
            )
            with patch.object(sniper, "queue_ingestion", side_effect=sqlite3.OperationalError("locked")), \
                 patch.object(sniper, "send_alert", return_value=True) as send:
                self.assertEqual(sniper.process_job(*args), 1)
                send.assert_called_once()
            status = conn.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-queue-write'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
        finally:
            conn.close()
            patches.close()

    def test_ingestion_serialization_failure_does_not_block_telegram(self):
        patches = ExitStack()
        patches.enter_context(patch.object(sniper, "DB_FILE", self.db_path))
        patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"))
        patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
        conn, _ = sniper.init_db()
        try:
            args = (
                conn, "job-serialize", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job-serialize", "TestATS", False, object(),
            )
            with patch.object(sniper, "queue_ingestion", side_effect=TypeError("not serializable")), \
                 patch.object(sniper, "send_alert", return_value=True) as send:
                self.assertEqual(sniper.process_job(*args), 1)
                send.assert_called_once()
            status = conn.execute(
                "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-serialize'"
            ).fetchone()[0]
            self.assertEqual(status, "sent")
        finally:
            conn.close()
            patches.close()

    def test_pending_ingestion_preserves_retry_state(self):
        patches = ExitStack()
        patches.enter_context(patch.object(sniper, "DB_FILE", self.db_path))
        patches.enter_context(patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"))
        patches.enter_context(patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"))
        conn, _ = sniper.init_db()
        try:
            payload = sniper.build_ingestion_payload(
                "job-retry-state", "Test", "Data Engineer", "Paris, France",
                "https://example.test/job-retry-state", "TestATS",
            )
            sniper.queue_ingestion(conn, payload)
            next_retry = "2099-01-01T00:00:00+00:00"
            conn.execute(
                "UPDATE supabase_ingestion_queue SET attempts = 4, next_attempt_at = ?, last_error = ? WHERE job_id = ?",
                (next_retry, "temporary failure", "job-retry-state"),
            )
            conn.commit()
            payload["title"] = "Updated Data Engineer"
            sniper.queue_ingestion(conn, payload)
            row = conn.execute(
                "SELECT payload_json, attempts, next_attempt_at, last_error, status FROM supabase_ingestion_queue WHERE job_id = ?",
                ("job-retry-state",),
            ).fetchone()
            self.assertIn("Updated Data Engineer", row[0])
            self.assertEqual(row[1:], (4, next_retry, "temporary failure", "pending"))
        finally:
            conn.close()
            patches.close()

    def test_enriched_sent_payload_is_redelivered_without_duplicate_notification(self):
        with patch.object(sniper, "DB_FILE", self.db_path), \
             patch.object(sniper, "INGESTION_API_URL", "http://ingest.test"), \
             patch.object(sniper, "INGESTION_SHARED_SECRET", "local-secret"):
            conn, _ = sniper.init_db()
            try:
                payload = sniper.build_ingestion_payload(
                    "enriched", "Test", "Data Engineer", "Paris, France",
                    "https://example.test/job", "TestATS",
                )
                sniper.queue_ingestion(conn, payload)
                conn.execute("UPDATE supabase_ingestion_queue SET status = 'sent'")
                conn.commit()
                payload["description"] = "Real provider description with requirements."
                sniper.queue_ingestion(conn, payload)
                self.assertEqual(conn.execute("SELECT status FROM supabase_ingestion_queue").fetchone()[0], "pending")
                conn.execute("UPDATE supabase_ingestion_queue SET status = 'sent', delivered_description = ?", (payload["description"],))
                conn.commit()
                sniper.queue_ingestion(conn, payload)
                self.assertEqual(conn.execute("SELECT status FROM supabase_ingestion_queue").fetchone()[0], "sent")
                payload["description"] = ""
                sniper.queue_ingestion(conn, payload)
                stored, status = conn.execute("SELECT payload_json, status FROM supabase_ingestion_queue").fetchone()
                self.assertIn("Real provider description", stored)
                self.assertEqual(status, "sent")
            finally:
                conn.close()

    def test_web_only_mode_never_calls_notifications(self):
        with patch.object(sniper, "DB_FILE", self.db_path), \
             patch.object(sniper, "WEB_ONLY_MODE", True), \
             patch.object(sniper, "INGESTION_API_URL", ""), \
             patch.object(sniper, "INGESTION_SHARED_SECRET", ""):
            conn, _ = sniper.init_db()
            try:
                args = (
                    conn, "job-web-only", "Test", "Data Engineer", "Paris, France",
                    "https://example.test/job-web-only", "TestATS", False, object(),
                )
                with patch.object(sniper, "send_alert") as send:
                    self.assertEqual(sniper.process_job(*args), 1)
                    send.assert_not_called()
                status = conn.execute(
                    "SELECT notification_status FROM seen_jobs WHERE job_id = 'job-web-only'"
                ).fetchone()[0]
                self.assertEqual(status, "baseline")
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

    def test_discord_and_telegram_failures_are_independent(self):
        class FailingSession:
            def __init__(self):
                self.calls = []

            def post(self, url, json, timeout):
                self.calls.append(url)
                raise sniper.requests.Timeout("simulated notification outage")

        session = FailingSession()
        with (
            patch.object(sniper, "DISCORD_WEBHOOK_URL", "https://discord.test/webhook"),
            patch.object(sniper, "TELEGRAM_BOT_TOKEN", "telegram-token"),
            patch.object(sniper, "TELEGRAM_CHAT_ID", "telegram-chat"),
        ):
            delivered = sniper.send_alert(
                "Test", "Data Engineer", "Paris", "https://example.test/job",
                "TestATS", session,
            )
        self.assertFalse(delivered)
        self.assertEqual(len(session.calls), 2)


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
