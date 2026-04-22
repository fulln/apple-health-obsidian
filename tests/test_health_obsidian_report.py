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

            self.assertIn("步数: 123 步", buffer.getvalue())

    def test_normalize_analysis_strips_ai_h1(self):
        text = "# Apple 健康日报｜2026-04-21\n\n## 今日结论\n- ok"

        self.assertEqual(report.normalize_analysis(text), "## 今日结论\n- ok")

    def test_render_markdown_omits_metric_detail_section(self):
        facts = {
            "date": "2026-04-21",
            "metrics_count": 1,
            "metrics": {"step_count": {"name": "step_count", "total": 123, "units": "count", "records": 2}},
            "workouts": {"count": 0, "duration_min": 0, "active_energy_kcal": 0, "items": []},
        }
        trends = {"period": "2026-04-15..2026-04-21", "metrics": [], "workout_days": 0, "workout_count": 0, "workout_duration_min": 0}
        markdown = report.render_markdown(
            dt.date(2026, 4, 21),
            Path("/health"),
            Path("/workout"),
            Path("/cache.json"),
            "raw metric facts",
            "## 总结\n- ok\n\n## 建议\n- move",
            facts,
            trends,
            None,
        )

        self.assertNotIn("## 指标明细", markdown)
        self.assertNotIn("raw metric facts", markdown)
        self.assertLess(markdown.index("## 总结"), markdown.index("## 建议"))
        self.assertLess(markdown.index("## 建议"), markdown.index("## 数据概览"))
        self.assertIn("| 指标 | 数值 |", markdown)

    def test_format_ai_frontmatter_uses_explicit_sections(self):
        formatted = report.format_ai_frontmatter(
            "## 总结\n- s1\n- s2\n\n## 建议\n- a1\n- a2\n- a3\n\n## 其他\n- ignored"
        )

        self.assertIn("## 总结\n\n- s1\n- s2", formatted)
        self.assertIn("## 建议\n\n- a1\n- a2\n- a3", formatted)
        self.assertNotIn("ignored", formatted)

    def test_infer_output_dir_uses_explicit_path(self):
        explicit = Path("/tmp/custom-vault/life/body")

        self.assertEqual(report.infer_output_dir(explicit), explicit)


if __name__ == "__main__":
    unittest.main()
