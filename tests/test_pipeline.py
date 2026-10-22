"""End-to-end checks for merge + render, without a browser.

Run with:  python -m unittest discover tests
"""

import datetime as dt
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import djb  # noqa: E402

CONFIG = ROOT / "tests" / "fixtures" / "config.yaml"


def iso(hours_ago: float) -> str:
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)
    return t.strftime("%Y-%m-%dT%H:%MZ")


LINKEDIN = {
    "source": "linkedin",
    "status": "done",
    "scanned": 10,
    "jobs": [
        # Same role as builtin b1 -> should merge into one entry on 2 boards.
        {"id": "1", "title": "Sr. Product Manager, Platform", "company": "Initech Inc.", "location": "New York, NY",
         "posted_label": "2 hours ago", "posted_at": iso(2), "salary": "$160,000.00/yr - $190,000.00/yr",
         "applicants": "Be among the first 25 applicants", "employment_type": "Full-time",
         "yoe": "5+ years of product management"},
        {"id": "2", "title": "Product Manager, Payments", "company": "Acme", "posted_at": iso(3)},   # applied -> dropped
        {"id": "3", "title": "Product Manager, Growth", "company": "Acme", "posted_at": iso(3)},     # pipeline note
        {"id": "4", "title": "Director, Product Manager", "company": "Hooli", "posted_at": iso(1)},  # excluded title
        {"id": "5", "title": "Product Manager", "company": "Old Co", "posted_at": iso(40)},          # too old
        {"id": "6", "title": "Product Manager", "company": "Senior Co", "posted_at": iso(1), "yoe": "10+ years"},
        {"id": "7", "title": "Product Manager", "company": "Cheap Co", "posted_at": iso(1), "salary": "$60,000 - $80,000"},
        {"id": "8", "title": "Product Manager", "company": "Part Co", "posted_at": iso(1), "employment_type": "Part-time"},
        {"id": "9", "title": "Product Manager, Data", "company": "Globex", "posted_at": iso(5)},     # company-only pipeline
    ],
}
BUILTIN = {
    "source": "builtin",
    "status": "done",
    "scanned": 5,
    "jobs": [
        {"id": "b1", "title": "Senior Product Manager - Platform", "company": "Initech",
         "url": "https://www.builtinnyc.com/job/x/b1", "posted_label": "Yesterday", "posted_at": iso(24),
         "salary": "150K-190K Annually"},
        {"id": "b2", "title": "Product Manager", "company": "Lowpay", "url": "https://www.builtinnyc.com/job/y/b2",
         "posted_label": "3 Hours Ago", "posted_at": iso(3), "salary": "110K-130K Annually"},
    ],
}


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())
        (self.run_dir / "raw").mkdir()
        # One export as page text with markers, one as bare JSON: both must parse.
        (self.run_dir / "raw" / "linkedin.txt").write_text(
            "Title: daily-job-board export\n---\nDJB_EXPORT_BEGIN" + json.dumps(LINKEDIN) + "DJB_EXPORT_END\n"
        )
        (self.run_dir / "raw" / "builtin.json").write_text(json.dumps(BUILTIN))
        self.cfg = djb.load_config(str(CONFIG))

    def tearDown(self):
        shutil.rmtree(self.run_dir)

    def merge(self):
        args = type("A", (), {"run": str(self.run_dir)})
        djb.cmd_merge(self.cfg, args)
        return json.loads((self.run_dir / "candidates.json").read_text())

    def test_filters_and_cross_listing(self):
        data = self.merge()
        by_company = {r["company"]: r for r in data["candidates"]}
        self.assertEqual(set(by_company), {"Initech Inc.", "Acme", "Globex", "Lowpay"})

        initech = by_company["Initech Inc."]
        self.assertEqual([b["label"] for b in initech["boards"]], ["LinkedIn", "Built In"])
        self.assertEqual(initech["url"], "https://www.linkedin.com/jobs/view/1")  # rebuilt from the id
        self.assertEqual(initech["applicants"], "Under 25 applicants")
        self.assertEqual(initech["salary"], "$160K–$190K")
        self.assertEqual(initech["yoe"], "5+ yrs")
        # The exact LinkedIn time wins over Built In's coarse "Yesterday".
        self.assertEqual(initech["posted_at"], LINKEDIN["jobs"][0]["posted_at"])

        self.assertEqual(by_company["Acme"]["title"], "Product Manager, Growth")
        self.assertIn("Product Manager, Payments", by_company["Acme"]["pipeline"])
        self.assertTrue(by_company["Globex"]["pipeline"].startswith("In your pipeline"))
        self.assertTrue(by_company["Lowpay"]["below_pay_target"])

        dropped = data["dropped"]
        for reason in ("already applied", "title excluded", "older than window", "asks for too many years",
                       "pay below minimum", "employment type"):
            self.assertEqual(dropped.get(reason), 1, reason)

        # Roles on more boards sort first.
        self.assertEqual(data["candidates"][0]["company"], "Initech Inc.")

    def test_render_with_scores(self):
        data = self.merge()
        keys = {r["company"]: r["key"] for r in data["candidates"]}
        (self.run_dir / "scores.json").write_text(json.dumps({
            keys["Initech Inc."]: {"tier": "apply_first", "why": "Platform PM in NYC."},
            keys["Lowpay"]: {"tier": "maybe", "why": "Pay is low."},
        }))
        args = type("A", (), {"run": str(self.run_dir)})
        djb.cmd_render(self.cfg, args)
        html = (self.run_dir / "report.html").read_text()
        text = (self.run_dir / "report.txt").read_text()
        self.assertIn("Apply first", html)
        self.assertIn("On 2 boards", html)
        self.assertIn("Seen on:", html)
        self.assertIn("https://www.builtinnyc.com/job/x/b1", html)
        self.assertNotIn("Acme", html)  # unscored -> skipped once scores exist
        self.assertIn("Platform PM in NYC.", text)
        self.assertTrue((self.run_dir / "subject.txt").read_text().startswith("Daily job board"))

    def test_helpers(self):
        self.assertEqual(djb.pretty_salary("$22.48-$37.44"), "$22.48–$37.44/hr")
        self.assertEqual(djb.pretty_salary("150K-205K Annually"), "$150K–$205K")
        self.assertEqual(djb.salary_max("$128,000 to $252,500."), 252500)
        self.assertIsNone(djb.short_years("130 years"))
        self.assertEqual(djb.short_years("3 to 4 years of experience"), "3–4 yrs")
        self.assertEqual(djb.norm_title("Sr. Product Manager - Remote"), "senior product manager")
        self.assertEqual(djb.norm_company("Fanduel"), djb.norm_company("FanDuel"))
        self.assertTrue(re.search(djb.phrases_regex(["head of"]), "Head of Product", re.I))
        self.assertFalse(re.search(djb.phrases_regex(["VP"]), "MVP Product Manager", re.I))


if __name__ == "__main__":
    unittest.main()
