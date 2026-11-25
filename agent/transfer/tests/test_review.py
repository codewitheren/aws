"""Regression coverage for approval boundaries and the 24.11 İzmir reference."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

AGENT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(AGENT), str(AGENT / "transfer")]

from analytics import metrics, query
from preflight import history_paths
from transfer_runs import approved_revisions, review_page, run_worker
from workflow import prepare, relex_path

SNAPSHOT = AGENT.parent / "data/data/gsheet_kopya_24.11"
JOB = dict(kind="cold", center="İzmir", date="2026-11-24")


class ReviewTest(unittest.TestCase):
    def test_authorizes_only_reviewed_batch_values_after_official_approval(self):
        edit = dict(depotCode="d1", productCode="p1", current=48, batch=6)
        checks = [{"id": str(n), "level": "uyari", "edits": [edit]} for n in range(1, 12)]
        state = dict(stage="review", checks=checks)
        page = review_page(state, 0)
        self.assertEqual((len(page["checks"]), page["remaining"]), (10, 1))
        decisions = {c["id"]: None for c in page["checks"]}
        decisions["1"] = [6]
        request = dict(approveOfficial=True, leaveRemaining=True, decisions=decisions)
        revisions, _ = approved_revisions(state, request)
        self.assertEqual(revisions[0]["value"], 6)
        for invalid in (dict(request, approveOfficial=False), dict(request, leaveRemaining=False),
                        dict(request, decisions={**decisions, "11": [6]}),
                        dict(request, decisions={**decisions, "1": [7]})):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                approved_revisions(state, invalid)
        with self.assertRaises(ValueError):
            approved_revisions(dict(state, stage="blocked"), request)

    def test_stale_inputs_stop_before_draft(self):
        with patch("workflow.run_motor") as motor:
            result = prepare_fixture_in_context(dict(JOB, date="2026-11-26"))
        self.assertTrue(result["blocked"])
        self.assertIsNone(result["draft"])
        motor.assert_not_called()

    def test_archive_excludes_run_day_and_keeps_last_three(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for when in ("19.11", "20.11", "21.11", "2026-11-23", "24.11"):
                path = root / when / "+4" / "İzmir.parquet"
                path.parent.mkdir(parents=True)
                path.touch()
            with patch.dict("os.environ", {"TRANSFER_HISTORY_DIR": directory, "TRANSFER_RUN_HISTORY_DIR": ""}):
                self.assertEqual([when for when, _ in history_paths("İzmir", "2026-11-24", "cold")],
                                 ["2026-11-23", "2026-11-21", "2026-11-20"])
                self.assertEqual(history_paths("İzmir", "2026-11-24", "cold", include_day=True)[0][0],
                                 "2026-11-24")

    def test_bulk_and_packaged_quantities_are_independent(self):
        data = pd.DataFrame({"Effective_Units": [12, 2, 8], "Final_Quantity": [6, 4, 1],
            "Trim_Reason": ["Sayım", "Onaylandi", "Sayım"], "Vol_Per_Unit": [1, 1, 1],
            "Is_Bulk": [False, False, True]})
        stats = metrics("ms", data)
        packs, bulk = [stats["quantities"][key] for key in ("adet", "kg")]
        self.assertEqual((packs["cut"], packs["proposed"], packs["cutPct"]), (6, 14, 42.86))
        self.assertEqual((bulk["cut"], bulk["proposed"], bulk["cutPct"]), (7, 8, 87.5))

    def test_official_revision_and_isolated_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SNAPSHOT, root / "snapshot")
            original = relex_path(root / "snapshot", "cold").read_bytes()
            activity = []
            review = run_worker(root, dict(JOB, action="prepare"), activity.append)
            self.assertFalse(review["blocked"])
            self.assertEqual(activity[0]["code"], "pandas.read_excel(...)")
            self.assertEqual(activity[-1]["title"], "İnceleme bulguları hazır")
            self.assertEqual(len(review["motorHash"]), 64)
            found = next(check for check in review["checks"] if check.get("edits"))
            edit = found["edits"][0]
            self.assertEqual((edit["depot"], edit["domain"], edit["current"], edit["proposed"]), ("Egekent", "G10", 48, 6))
            decisions = {c["id"]: None for c in review_page(review, 0)["checks"] if c["level"] == "uyari"}
            decisions[found["id"]] = [6]
            revisions, reviewed = approved_revisions(dict(review, stage="review"),
                dict(approveOfficial=True, leaveRemaining=True, decisions=decisions))
            official_job = dict(JOB, checks=review["checks"], action="finish", revisions=revisions,
                                reviewed=reviewed, motorHash=review["motorHash"])
            activity.clear()
            official = run_worker(root, official_job, activity.append)
            self.assertEqual([e["kind"] for e in activity], ["data", "command", "output", "command", "check"])
            self.assertIn("1 satıra onaylı miktar yazıldı", activity[0]["detail"])
            self.assertEqual(official["summary"]["revised"][0]["final"], 6)
            self.assertIn("revize_log.csv", official["files"])
            self.assertEqual(relex_path(root / "snapshot", "cold").read_bytes(), original)
            baseline = Path(official["files"]["transfer.parquet"])
            metrics = query("cold", pd.read_parquet(baseline), depot="Kepez", why=True)
            self.assertEqual(metrics["quantities"]["adet"]["cut"], 101)
            self.assertEqual(metrics["quantities"]["adet"]["reasons"][0]["reason"], "Dolap hacmi (ETB)")
            with tempfile.TemporaryDirectory() as scenario_directory:
                scenario_root = Path(scenario_directory)
                shutil.copytree(root / "snapshot", scenario_root / "snapshot")
                shutil.copy2(baseline, scenario_root / "baseline.parquet")
                whatif = run_worker(scenario_root, dict(official_job, action="scenario", summary=official["summary"],
                    change=dict(type="buffer", depot="Bir Eylül", value=1.2)))
                self.assertEqual([whatif["target"][k]["quantities"]["adet"]["final"] for k in ("before", "after")],
                                 [997, 1178])
                self.assertEqual(relex_path(scenario_root / "snapshot", "cold").read_bytes(), original)
                self.assertTrue(whatif["limits"]["before"])
                self.assertTrue(whatif["limits"]["after"])


def prepare_fixture_in_context(job):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(SNAPSHOT, root / "snapshot")
        return prepare(root, job)


if __name__ == "__main__":
    unittest.main()
