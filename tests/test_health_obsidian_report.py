import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import health_obsidian_report as report


class HealthObsidianReportTest(unittest.TestCase):
    def test_build_facts_aggregates_core_metrics(self):
        payload = {
            "data": {
                "metrics": [
                    {
                        "name": "step_count",
                        "units": "count",
                        "data": [{"qty": 100}, {"qty": "250"}],
                    },
                    {
                        "name": "active_energy",
                        "units": "kJ",
                        "data": [{"qty": 418.4}],
                    },
                    {
                        "name": "sleep_analysis",
                        "units": "hr",
                        "data": [{"totalSleep": 7.25, "deep": 1.2, "rem": 1.5}],
                    },
                    {
                        "name": "heart_rate",
                        "units": "count/min",
                        "data": [{"Avg": 70, "Min": 55, "Max": 120}],
                    },
                ]
            }
        }

        facts = report.build_health_facts(payload, dt.date(2026, 4, 21), None)

        self.assertEqual(facts["metrics"]["step_count"]["total"], 350)
        self.assertEqual(facts["metrics"]["active_energy"]["kcal"], 100)
        self.assertEqual(facts["metrics"]["sleep_analysis"]["totalSleep"], 7.25)
        self.assertEqual(facts["metrics"]["heart_rate"]["avg"], 70)

    def test_main_dry_run_does_not_create_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "vault" / "life" / "body"
            archive = output / "health-json"
            source.mkdir()
            payload = {
                "data": {
                    "metrics": [
                        {"name": "step_count", "units": "count", "data": [{"qty": 1}]}
                    ]
                }
            }
            (source / "HealthAutoExport-2026-04-21.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            old_argv = sys.argv
            sys.argv = [
                "health_obsidian_report.py",
                "--source-dir",
                str(source),
                "--output-dir",
                str(output),
                "--date",
                "2026-04-21",
                "--no-ai",
                "--dry-run",
            ]
            buffer = io.StringIO()
            try:
                with redirect_stdout(buffer):
                    self.assertEqual(report.main(), 0)
            finally:
                sys.argv = old_argv

            self.assertFalse(archive.exists())
            self.assertFalse((output / ".apple-health-cache").exists())
            self.assertIn("Would write", buffer.getvalue())

    def test_autosync_health_dir_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            health = root / "HealthMetrics"
            workout = root / "Workouts"
            output = root / "vault" / "life" / "body"
            (health / "step_count").mkdir(parents=True)
            workout.mkdir()
            (health / "step_count" / "20260421.hae").write_text("placeholder", encoding="utf-8")

            old_read_hae = report.read_hae
            report.read_hae = lambda path: {
                "data": [{"qty": 100, "unit": "count"}, {"qty": 23, "unit": "count"}]
            }
            old_argv = sys.argv
            sys.argv = [
                "health_obsidian_report.py",
                "--health-dir",
                str(health),
                "--workout-dir",
                str(workout),
                "--output-dir",
                str(output),
                "--date",
                "2026-04-21",
                "--no-ai",
                "--dry-run",
            ]
            buffer = io.StringIO()
            try:
                with redirect_stdout(buffer):
                    self.assertEqual(report.main(), 0)
            finally:
                report.read_hae = old_read_hae
                sys.argv = old_argv

            self.assertIn("step_count", buffer.getvalue())
            self.assertIn("total=123count", buffer.getvalue())

    def test_normalize_analysis_strips_ai_h1(self):
        text = "# Apple 健康日报｜2026-04-21\n\n## 今日结论\n- ok"

        self.assertEqual(report.normalize_analysis(text), "## 今日结论\n- ok")


if __name__ == "__main__":
    unittest.main()
