#!/usr/bin/env python3
"""Generate an Obsidian Apple Health daily note from Health Auto Export JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_DIR = Path(
    "/Users/fulln/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/data"
)
DEFAULT_OUTPUT_DIR = Path("/Users/fulln/opt/TIL/life/body")
DEFAULT_ARCHIVE_NAME = "health-json"
DEFAULT_AI_TIMEOUT = 180

SUM_METRICS = {
    "step_count",
    "apple_exercise_time",
    "apple_stand_time",
    "apple_stand_hour",
    "active_energy",
    "basal_energy_burned",
    "walking_running_distance",
    "time_in_daylight",
    "handwashing",
}

AVERAGE_METRICS = {
    "heart_rate",
    "resting_heart_rate",
    "walking_heart_rate_average",
    "heart_rate_variability",
    "blood_oxygen_saturation",
    "respiratory_rate",
    "walking_speed",
    "walking_step_length",
    "walking_double_support_percentage",
    "walking_asymmetry_percentage",
    "stair_speed_down",
    "physical_effort",
    "headphone_audio_exposure",
}

LATEST_METRICS = {
    "weight_body_mass",
    "body_mass_index",
    "body_fat_percentage",
    "lean_body_mass",
    "six_minute_walking_test_distance",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--ai-command", help="Command that reads prompt from stdin.")
    parser.add_argument("--ai-timeout", type=int, default=DEFAULT_AI_TIMEOUT)
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing note.")
    return parser.parse_args()


def report_date(value: str | None) -> dt.date:
    if value:
        return dt.date.fromisoformat(value)
    return dt.date.today() - dt.timedelta(days=1)


def load_export(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def round_value(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def metric_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metrics = payload.get("data", {}).get("metrics", [])
    if not isinstance(metrics, list):
        raise ValueError("Expected data.metrics to be a list")
    result: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        if isinstance(metric, dict) and metric.get("name"):
            result[str(metric["name"])] = metric
    return result


def qty_values(records: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for record in records:
        value = as_float(record.get("qty"))
        if value is not None:
            values.append(value)
    return values


def aggregate_metric(name: str, metric: dict[str, Any]) -> dict[str, Any]:
    records = metric.get("data", [])
    if not isinstance(records, list):
        records = []
    records = [record for record in records if isinstance(record, dict)]
    units = metric.get("units", "")
    values = qty_values(records)
    summary: dict[str, Any] = {
        "name": name,
        "units": units,
        "records": len(records),
    }

    if name == "sleep_analysis":
        summary.update(aggregate_sleep(records))
        return summary

    if name == "heart_rate":
        avg_values = [as_float(record.get("Avg")) for record in records]
        min_values = [as_float(record.get("Min")) for record in records]
        max_values = [as_float(record.get("Max")) for record in records]
        avg_values = [value for value in avg_values if value is not None]
        min_values = [value for value in min_values if value is not None]
        max_values = [value for value in max_values if value is not None]
        if avg_values:
            summary["avg"] = round_value(sum(avg_values) / len(avg_values), 1)
        if min_values:
            summary["min"] = round_value(min(min_values), 1)
        if max_values:
            summary["max"] = round_value(max(max_values), 1)
        return summary

    if not values:
        return summary

    if name in SUM_METRICS:
        summary["total"] = round_value(sum(values), 2)
    elif name in LATEST_METRICS:
        summary["latest"] = round_value(values[-1], 2)
    else:
        summary["avg"] = round_value(sum(values) / len(values), 2)

    if name in AVERAGE_METRICS or name not in SUM_METRICS | LATEST_METRICS:
        summary["min"] = round_value(min(values), 2)
        summary["max"] = round_value(max(values), 2)

    if name in {"active_energy", "basal_energy_burned"} and units == "kJ":
        summary["kcal"] = round_value(sum(values) / 4.184, 1)

    return summary


def aggregate_sleep(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    record = records[-1]
    fields = ["totalSleep", "deep", "rem", "core", "awake", "inBed"]
    summary: dict[str, Any] = {}
    for field in fields:
        value = as_float(record.get(field))
        if value is not None:
            summary[field] = round_value(value, 2)
    for field in ["sleepStart", "sleepEnd", "inBedStart", "inBedEnd"]:
        if record.get(field):
            summary[field] = record[field]
    return summary


def build_facts(payload: dict[str, Any], date: dt.date) -> dict[str, Any]:
    metrics = metric_records(payload)
    summaries = {
        name: aggregate_metric(name, metric)
        for name, metric in sorted(metrics.items())
    }
    return {
        "date": date.isoformat(),
        "metrics_count": len(summaries),
        "metrics": summaries,
    }


def format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def metric_line(summary: dict[str, Any]) -> str:
    name = summary["name"]
    units = summary.get("units", "")
    parts = [f"records={summary.get('records', 0)}"]
    for key in ["total", "kcal", "latest", "avg", "min", "max"]:
        if key in summary:
            suffix = "kcal" if key == "kcal" else units
            parts.append(f"{key}={format_number(summary[key])}{suffix}")
    for key in ["totalSleep", "deep", "rem", "core", "awake", "inBed"]:
        if key in summary:
            parts.append(f"{key}={format_number(summary[key])}hr")
    return f"- {name}: " + ", ".join(parts)


def compact_facts_markdown(facts: dict[str, Any]) -> str:
    metrics = facts["metrics"]
    priority = [
        "step_count",
        "walking_running_distance",
        "apple_exercise_time",
        "apple_stand_hour",
        "apple_stand_time",
        "active_energy",
        "basal_energy_burned",
        "sleep_analysis",
        "resting_heart_rate",
        "heart_rate",
        "heart_rate_variability",
        "walking_heart_rate_average",
        "blood_oxygen_saturation",
        "respiratory_rate",
        "time_in_daylight",
        "walking_speed",
        "walking_step_length",
        "weight_body_mass",
        "body_fat_percentage",
        "body_mass_index",
    ]
    lines = [f"日期: {facts['date']}", f"指标数量: {facts['metrics_count']}"]
    lines.append("")
    lines.append("重点指标:")
    for name in priority:
        if name in metrics:
            lines.append(metric_line(metrics[name]))
    other_names = [name for name in metrics if name not in priority]
    if other_names:
        lines.append("")
        lines.append("其他指标:")
        for name in other_names:
            lines.append(metric_line(metrics[name]))
    return "\n".join(lines)


def fallback_analysis(facts: dict[str, Any]) -> str:
    metrics = facts["metrics"]

    def get(name: str, key: str) -> Any:
        return metrics.get(name, {}).get(key)

    rows = [
        ("步数", get("step_count", "total"), "步"),
        ("步行/跑步距离", get("walking_running_distance", "total"), "km"),
        ("锻炼时间", get("apple_exercise_time", "total"), "min"),
        ("站立小时", get("apple_stand_hour", "total"), "h"),
        ("活动能量", get("active_energy", "kcal"), "kcal"),
        ("睡眠", get("sleep_analysis", "totalSleep"), "hr"),
        ("静息心率", get("resting_heart_rate", "avg") or get("resting_heart_rate", "latest"), "次/分"),
        ("HRV", get("heart_rate_variability", "avg"), "ms"),
    ]
    lines = ["## AI 总结", "", "AI 未运行或未成功返回，以下是自动指标摘要：", ""]
    for label, value, unit in rows:
        if value is not None:
            lines.append(f"- {label}: {format_number(value)} {unit}")
    lines.extend([
        "",
        "## 初步判断",
        "",
        "- 优先看步数、锻炼时间、活动能量与睡眠是否同时达标。",
        "- 若活动量高但睡眠或 HRV 偏低，第二天应降低训练强度。",
        "- 若步数和锻炼时间偏低，安排一段低门槛步行作为补偿。",
    ])
    return "\n".join(lines)


def normalize_analysis(text: str) -> str:
    lines = text.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def ai_prompt(facts_md: str) -> str:
    return f"""你是一个谨慎的 Apple 健康与运动数据分析助手。

请基于下面的确定性汇总数据，用中文写一份 Obsidian Markdown 日报。

要求：
- 不要假装知道未提供的数据。
- 先给 3-5 条结论，再分别分析活动、运动、睡眠/恢复、心肺、身体指标。
- 给出今天可执行的 3 条建议，建议要具体、保守、可执行。
- 如果数据缺失，明确写出缺失项。
- 不做医疗诊断；涉及异常时建议持续观察或咨询专业人士。
- 不要输出一级标题，直接从二级标题开始。
- 直接输出 Markdown 正文，不要包裹代码块。

数据：
{facts_md}
"""


def run_ai(command: str | None, prompt: str, timeout: int) -> tuple[str | None, str | None]:
    resolved = command or os.environ.get("HEALTH_OBSIDIAN_AI_COMMAND")
    if not resolved:
        codex = shutil.which("codex") or "codex"
        resolved = f"{shlex.quote(codex)} exec --ephemeral --skip-git-repo-check --sandbox read-only --model gpt-5.4-mini -"
    args = shlex.split(resolved)
    try:
        completed = subprocess.run(
            args,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    output = completed.stdout.strip()
    if completed.returncode != 0 or not output:
        error = completed.stderr.strip() or f"AI command exited {completed.returncode}"
        return None, error
    return output, None


def sync_jsons(source_dir: Path, archive_dir: Path, dry_run: bool) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    copied: list[Path] = []
    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.glob("HealthAutoExport-*.json")):
        target = archive_dir / source.name
        should_copy = not target.exists() or source.stat().st_size != target.stat().st_size
        if should_copy:
            copied.append(target)
            if not dry_run:
                shutil.copy2(source, target)
    return copied


def render_markdown(
    date: dt.date,
    source_json: Path,
    archive_dir: Path,
    facts: dict[str, Any],
    facts_md: str,
    analysis: str,
    ai_error: str | None,
) -> str:
    title = f"健康日报 {date.isoformat()}"
    frontmatter = [
        "---",
        f"title: {title}",
        f"date: {date.isoformat()}",
        "tags:",
        "  - health/apple",
        "  - life/body",
        f"source_json: {source_json.name}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    body = [normalize_analysis(analysis), "", "## 指标明细", "", facts_md, ""]
    body.extend([
        "## 同步信息",
        "",
        f"- 原始文件: `{source_json}`",
        f"- Obsidian 归档: `{archive_dir / source_json.name}`",
        f"- 生成时间: {dt.datetime.now().isoformat(timespec='seconds')}",
    ])
    if ai_error:
        body.extend(["", "## AI 运行状态", "", f"- AI 未成功返回: `{ai_error[:500]}`"])
    return "\n".join(frontmatter + body).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    date = report_date(args.date)
    source_json = args.source_dir / f"HealthAutoExport-{date.isoformat()}.json"
    archive_dir = args.archive_dir or (args.output_dir / DEFAULT_ARCHIVE_NAME)
    note_path = args.output_dir / f"健康日报-{date.isoformat()}.md"

    if not source_json.exists():
        print(f"Missing source JSON: {source_json}", file=sys.stderr)
        return 2
    if note_path.exists() and not args.force and not args.dry_run:
        print(f"Note already exists, use --force to overwrite: {note_path}", file=sys.stderr)
        return 3

    copied = sync_jsons(args.source_dir, archive_dir, args.dry_run)
    payload = load_export(source_json)
    facts = build_facts(payload, date)
    facts_md = compact_facts_markdown(facts)

    ai_error = None
    analysis = None
    if not args.no_ai:
        analysis, ai_error = run_ai(args.ai_command, ai_prompt(facts_md), args.ai_timeout)
    if not analysis:
        analysis = fallback_analysis(facts)

    markdown = render_markdown(date, source_json, archive_dir, facts, facts_md, analysis, ai_error)

    if args.dry_run:
        print(f"Would sync {len(copied)} JSON file(s) into {archive_dir}")
        print(f"Would write {note_path}")
        print(markdown)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    note_path.write_text(markdown, encoding="utf-8")
    print(f"Synced {len(copied)} JSON file(s) into {archive_dir}")
    print(f"Wrote {note_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
