import unittest
from unittest.mock import patch

from scripts.enrich_jobs import Enriched, extract_json_or_page, is_complete_description, merge_fields, provider_from


class EnrichmentTests(unittest.TestCase):
    def test_completeness_requires_meaningful_content(self):
        self.assertFalse(is_complete_description("Short title only"))
        text = "Responsibilities include building data pipelines and models for production analytics teams. Requirements include Python, SQL, testing, and clear written communication. The role works with stakeholders to define reliable metrics, document decisions, and improve delivery quality across several projects."
        self.assertTrue(is_complete_description(text))

    def test_provider_detection(self):
        self.assertEqual(provider_from("Greenhouse", "https://boards.greenhouse.io/acme/jobs/42"), "greenhouse")
        self.assertEqual(provider_from("HelloWork", "https://www.hellowork.com/emplois/42.html"), "hellowork")

    @patch("scripts.enrich_jobs.fetch_public")
    def test_greenhouse_public_detail_is_extracted(self, fetch):
        fetch.return_value = ('{"content":"<p>Responsibilities include Python data work. Requirements include SQL. Collaborate with the team.</p>","location":{"name":"Paris"}}', "application/json")
        job = {"canonical_url": "https://boards.greenhouse.io/acme/jobs/42", "job_sources": [{"source_url": "https://boards.greenhouse.io/acme/jobs/42"}]}
        result = extract_json_or_page("greenhouse", job)
        self.assertIn("Responsibilities", result.description)
        self.assertEqual(result.location, "Paris")

    def test_merge_preserves_existing_description(self):
        existing = {"description": "Existing complete description. Responsibilities are clear. Requirements are listed.", "location": "Paris", "remote_type": None}
        fields = merge_fields(existing, Enriched(description="New description that should not replace the existing value.", location="Lyon", remote_type="remote"))
        self.assertNotIn("description", fields)
        self.assertNotIn("location", fields)
        self.assertEqual(fields["remote_type"], "remote")


if __name__ == "__main__":
    unittest.main()
