#!/usr/bin/env python3
"""Generate an Obsidian Apple Health daily note from synced JSON files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DOCUMENTS_DIR = Path(
    "/Users/fulln/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents"
)
AUTOSYNC_DIR = DOCUMENTS_DIR / "AutoSync"
DEFAULT_HEALTH_DIR = DOCUMENTS_DIR / "health"
DEFAULT_WORKOUT_DIR = DOCUMENTS_DIR / "workout"
AUTOSYNC_HEALTH_DIR = AUTOSYNC_DIR / "HealthMetrics"
AUTOSYNC_WORKOUT_DIR = AUTOSYNC_DIR / "Workouts"
LEGACY_HEALTH_DIR = DOCUMENTS_DIR / "New Automation"
DEFAULT_OUTPUT_DIR = Path("/Users/fulln/opt/TIL/life/body")
DEFAULT_CACHE_NAME = ".apple-health-cache/daily-facts.json"
DEFAULT_AI_TIMEOUT = 180
COMPRESSION_TOOL = "/usr/bin/compression_tool"

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
    "flights_climbed",
    "swimming_distance",
    "swimming_stroke_count",
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
    "vo2_max",
}

LATEST_METRICS = {
    "weight_body_mass",
    "body_mass_index",
    "body_fat_percentage",
    "lean_body_mass",
    "six_minute_walking_test_distance",
}

PRIORITY_METRICS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-dir", type=Path, default=None)
    parser.add_argument("--workout-dir", type=Path, default=None)
    parser.add_argument("--source-dir", type=Path, help="Backward-compatible alias for --health-dir.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cache-file", type=Path)
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--lookback-days", type=int, default=7)
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


def date_range(end: dt.date, days: int) -> list[dt.date]:
    return [end - dt.timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def resolve_health_dir(args: argparse.Namespace) -> Path:
    if args.health_dir:
        return args.health_dir
    if args.source_dir:
        return args.source_dir
    if DEFAULT_HEALTH_DIR.exists():
        return DEFAULT_HEALTH_DIR
    if AUTOSYNC_HEALTH_DIR.exists():
        return AUTOSYNC_HEALTH_DIR
    return LEGACY_HEALTH_DIR


def resolve_workout_dir(args: argparse.Namespace) -> Path:
    if args.workout_dir:
        return args.workout_dir
    if DEFAULT_WORKOUT_DIR.exists():
        return DEFAULT_WORKOUT_DIR
    return AUTOSYNC_WORKOUT_DIR


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


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_hae(path: Path) -> Any:
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        completed = subprocess.run(
            [COMPRESSION_TOOL, "-decode", "-a", "lzfse", "-i", str(path), "-o", str(temp_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"Failed to decode {path}: {detail}")
        return json.loads(temp_path.read_text(encoding="utf-8"))
    finally:
        temp_path.unlink(missing_ok=True)


def health_json_path(health_dir: Path, date: dt.date) -> Path:
    candidates = [
        health_dir / f"HealthAutoExport-{date.isoformat()}.json",
        health_dir / f"{date.isoformat()}.json",
        health_dir / f"{date.strftime('%Y%m%d')}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(health_dir.rglob(f"*{date.isoformat()}*.json"))
    if matches:
        return matches[0]
    matches = sorted(health_dir.rglob(f"*{date.strftime('%Y%m%d')}*.json"))
    if matches:
        return matches[0]
    return candidates[0]


def is_autosync_health_dir(health_dir: Path) -> bool:
    return (health_dir / "step_count").is_dir() or (health_dir / "sleep_analysis").is_dir()


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


def aggregate_sleep(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    if len(records) == 1:
        record = records[-1]
        fields = ["totalSleep", "deep", "rem", "core", "awake", "inBed"]
        summary: dict[str, Any] = {}
        for field in fields:
            value = as_float(record.get(field))
            if value is not None:
                summary[field] = round_value(value, 2)
        return summary

    summary = {}
    for field in ["totalSleep", "deep", "rem", "core", "awake", "inBed"]:
        values = [as_float(record.get(field)) for record in records]
        values = [value for value in values if value is not None]
        if values:
            summary[field] = round_value(sum(values), 2)
    summary["segments"] = len(records)
    return summary


def aggregate_metric(name: str, metric: dict[str, Any]) -> dict[str, Any]:
    records = metric.get("data", [])
    if not isinstance(records, list):
        records = []
    records = [record for record in records if isinstance(record, dict)]
    units = metric.get("units", "")
    values = qty_values(records)
    summary: dict[str, Any] = {"name": name, "units": units, "records": len(records)}

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


def aggregate_autosync_metric(metric_name: str, path: Path) -> dict[str, Any] | None:
    payload = read_hae(path)
    if not isinstance(payload, dict):
        return None
    records = payload.get("data", [])
    if not isinstance(records, list):
        records = []
    unit = ""
    for record in records:
        if isinstance(record, dict) and record.get("unit"):
            unit = str(record["unit"])
            break
    metric = {"name": metric_name, "units": unit, "data": records}
    return aggregate_metric(metric_name, metric)


def build_health_facts(payload: dict[str, Any], date: dt.date, source: Path | None) -> dict[str, Any]:
    metrics = metric_records(payload)
    summaries = {name: aggregate_metric(name, metric) for name, metric in sorted(metrics.items())}
    return {
        "date": date.isoformat(),
        "source": str(source) if source else None,
        "metrics_count": len(summaries),
        "metrics": summaries,
    }


def build_autosync_health_facts(health_dir: Path, date: dt.date) -> dict[str, Any]:
    metrics: dict[str, dict[str, Any]] = {}
    day_key = date.strftime("%Y%m%d")
    for metric_dir in sorted(path for path in health_dir.iterdir() if path.is_dir()):
        path = metric_dir / f"{day_key}.hae"
        if not path.exists():
            continue
        summary = aggregate_autosync_metric(metric_dir.name, path)
        if summary and summary.get("records", 0):
            metrics[metric_dir.name] = summary
    return {
        "date": date.isoformat(),
        "source": str(health_dir),
        "metrics_count": len(metrics),
        "metrics": metrics,
    }


def date_matches_path(path: Path, date: dt.date) -> bool:
    name = path.name
    return date.isoformat() in name or date.strftime("%Y%m%d") in name


def flatten_workout_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["workouts", "items", "records"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    for key in ["workouts", "data", "items", "records"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def nested_qty(value: Any) -> float | None:
    if isinstance(value, dict):
        return as_float(value.get("qty"))
    if isinstance(value, list):
        values = [nested_qty(item) for item in value]
        values = [item for item in values if item is not None]
        return sum(values) if values else None
    return as_float(value)


def normalize_workout(record: dict[str, Any], source: Path) -> dict[str, Any]:
    name = record.get("name") or record.get("workoutActivityType") or record.get("type") or source.stem
    duration = (
        as_float(record.get("duration_min"))
        or as_float(record.get("durationMinutes"))
        or as_float(record.get("duration"))
    )
    if duration is not None and duration > 240:
        duration = duration / 60
    active_energy = as_float(record.get("active_energy_kcal")) or as_float(record.get("activeEnergyKcal"))
    active_energy_kj = (
        nested_qty(record.get("activeEnergyBurned"))
        or as_float(record.get("activeEnergyKJ"))
        or as_float(record.get("active_energy_kj"))
    )
    raw_active_energy = nested_qty(record.get("activeEnergy")) or nested_qty(record.get("active_energy"))
    if active_energy is None and active_energy_kj is not None:
        active_energy = active_energy_kj / 4.184
    elif active_energy is None and raw_active_energy is not None:
        active_energy = raw_active_energy / 4.184 if source.suffix == ".hae" else raw_active_energy
    distance = nested_qty(record.get("distance")) or as_float(record.get("distance_km"))
    avg_hr = nested_qty(record.get("avgHeartRate"))
    max_hr = nested_qty(record.get("maxHeartRate"))
    return {
        key: value
        for key, value in {
            "name": str(name),
            "duration_min": round_value(duration, 1),
            "active_energy_kcal": round_value(active_energy, 1),
            "distance": round_value(distance, 2),
            "avg_heart_rate": round_value(avg_hr, 1),
            "max_heart_rate": round_value(max_hr, 1),
            "source": source.name,
        }.items()
        if value is not None
    }


def load_workouts(workout_dir: Path, date: dt.date) -> list[dict[str, Any]]:
    if not workout_dir.exists():
        return []
    workouts: list[dict[str, Any]] = []
    for path in sorted(workout_dir.rglob("*.json")):
        if not date_matches_path(path, date):
            continue
        payload = load_json(path)
        for record in flatten_workout_payload(payload):
            workouts.append(normalize_workout(record, path))
    for path in sorted(workout_dir.rglob("*.hae")):
        if not date_matches_path(path, date):
            continue
        payload = read_hae(path)
        for record in flatten_workout_payload(payload):
            workouts.append(normalize_workout(record, path))
    return workouts


def summarize_workouts(workouts: list[dict[str, Any]]) -> dict[str, Any]:
    duration = [as_float(workout.get("duration_min")) for workout in workouts]
    kcal = [as_float(workout.get("active_energy_kcal")) for workout in workouts]
    duration = [value for value in duration if value is not None]
    kcal = [value for value in kcal if value is not None]
    by_type: dict[str, int] = {}
    for workout in workouts:
        key = str(workout.get("name") or "Workout")
        by_type[key] = by_type.get(key, 0) + 1
    return {
        "count": len(workouts),
        "duration_min": round_value(sum(duration), 1) if duration else 0,
        "active_energy_kcal": round_value(sum(kcal), 1) if kcal else 0,
        "by_type": by_type,
        "items": workouts,
    }


def build_daily_facts(health_dir: Path, workout_dir: Path, date: dt.date) -> dict[str, Any]:
    if is_autosync_health_dir(health_dir):
        health = build_autosync_health_facts(health_dir, date)
    else:
        path = health_json_path(health_dir, date)
        if path.exists():
            health = build_health_facts(load_json(path), date, path)
        else:
            health = {"date": date.isoformat(), "source": None, "metrics_count": 0, "metrics": {}}
    health["workouts"] = summarize_workouts(load_workouts(workout_dir, date))
    return health


def cache_path(output_dir: Path, explicit: Path | None) -> Path:
    return explicit or (output_dir / DEFAULT_CACHE_NAME)


def read_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "days": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "days": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("days"), dict):
        return {"version": 1, "days": {}}
    return payload


def write_cache(path: Path, cache: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def update_cache(
    cache: dict[str, Any],
    health_dir: Path,
    workout_dir: Path,
    dates: list[dt.date],
) -> dict[str, dict[str, Any]]:
    days = cache.setdefault("days", {})
    result: dict[str, dict[str, Any]] = {}
    for day in dates:
        key = day.isoformat()
        facts = build_daily_facts(health_dir, workout_dir, day)
        days[key] = facts
        result[key] = facts
    return result


def trend_for_metric(history: list[dict[str, Any]], metric_name: str, field: str) -> dict[str, Any] | None:
    values: list[float] = []
    for day in history:
        value = day.get("metrics", {}).get(metric_name, {}).get(field)
        number = as_float(value)
        if number is not None:
            values.append(number)
    if not values:
        return None
    avg = sum(values) / len(values)
    return {
        "metric": metric_name,
        "field": field,
        "days": len(values),
        "avg": round_value(avg, 2),
        "min": round_value(min(values), 2),
        "max": round_value(max(values), 2),
        "latest": round_value(values[-1], 2),
        "delta_latest_vs_avg": round_value(values[-1] - avg, 2),
    }


def build_trends(history: list[dict[str, Any]]) -> dict[str, Any]:
    specs = [
        ("step_count", "total"),
        ("walking_running_distance", "total"),
        ("apple_exercise_time", "total"),
        ("active_energy", "kcal"),
        ("sleep_analysis", "totalSleep"),
        ("resting_heart_rate", "avg"),
        ("heart_rate_variability", "avg"),
        ("weight_body_mass", "latest"),
        ("body_fat_percentage", "latest"),
    ]
    metrics = [trend for name, field in specs if (trend := trend_for_metric(history, name, field))]
    workout_counts = [as_float(day.get("workouts", {}).get("count")) for day in history]
    workout_minutes = [as_float(day.get("workouts", {}).get("duration_min")) for day in history]
    workout_counts = [value for value in workout_counts if value is not None]
    workout_minutes = [value for value in workout_minutes if value is not None]
    return {
        "period": f"{history[0]['date']}..{history[-1]['date']}" if history else "",
        "metrics": metrics,
        "workout_days": sum(1 for value in workout_counts if value > 0),
        "workout_count": int(sum(workout_counts)) if workout_counts else 0,
        "workout_duration_min": round_value(sum(workout_minutes), 1) if workout_minutes else 0,
    }


def format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def display_value(value: Any, unit: str = "") -> str:
    if value is None:
        return "-"
    text = format_number(value)
    return f"{text} {unit}".strip()


def metric_value(metrics: dict[str, dict[str, Any]], name: str, *fields: str) -> Any:
    metric = metrics.get(name, {})
    for field in fields:
        if field in metric:
            return metric[field]
    return None


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


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) if cell is not None else "-" for cell in row) + " |")
    return "\n".join(lines)


def daily_overview_table(facts: dict[str, Any]) -> str:
    metrics = facts["metrics"]
    rows = [
        ["步数", display_value(metric_value(metrics, "step_count", "total"), "步")],
        ["步行/跑步距离", display_value(metric_value(metrics, "walking_running_distance", "total"), "km")],
        ["锻炼时间", display_value(metric_value(metrics, "apple_exercise_time", "total"), "min")],
        ["站立小时", display_value(metric_value(metrics, "apple_stand_hour", "total"), "h")],
        ["活动能量", display_value(metric_value(metrics, "active_energy", "kcal"), "kcal")],
        ["睡眠", display_value(metric_value(metrics, "sleep_analysis", "totalSleep"), "hr")],
        ["静息心率", display_value(metric_value(metrics, "resting_heart_rate", "avg", "latest"), "bpm")],
        ["HRV", display_value(metric_value(metrics, "heart_rate_variability", "avg"), "ms")],
        ["体重", display_value(metric_value(metrics, "weight_body_mass", "latest"), "kg")],
        ["体脂率", display_value(metric_value(metrics, "body_fat_percentage", "latest"), "%")],
    ]
    return markdown_table(["指标", "数值"], rows)


def workout_table(facts: dict[str, Any]) -> str:
    workouts = facts.get("workouts", {})
    items = workouts.get("items", [])
    if not items:
        return "无运动记录。"
    rows = []
    for item in items:
        rows.append([
            item.get("name", "-"),
            display_value(item.get("duration_min"), "min"),
            display_value(item.get("active_energy_kcal"), "kcal"),
            display_value(item.get("distance"), "km"),
            display_value(item.get("avg_heart_rate"), "bpm"),
            display_value(item.get("max_heart_rate"), "bpm"),
        ])
    rows.append([
        "合计",
        display_value(workouts.get("duration_min"), "min"),
        display_value(workouts.get("active_energy_kcal"), "kcal"),
        "-",
        "-",
        "-",
    ])
    return markdown_table(["运动", "时长", "活动能量", "距离", "平均心率", "最高心率"], rows)


def trend_label(metric: str, field: str) -> str:
    labels = {
        ("step_count", "total"): "步数",
        ("walking_running_distance", "total"): "步行/跑步距离",
        ("apple_exercise_time", "total"): "锻炼时间",
        ("active_energy", "kcal"): "活动能量",
        ("sleep_analysis", "totalSleep"): "睡眠",
        ("resting_heart_rate", "avg"): "静息心率",
        ("heart_rate_variability", "avg"): "HRV",
        ("weight_body_mass", "latest"): "体重",
        ("body_fat_percentage", "latest"): "体脂率",
    }
    return labels.get((metric, field), f"{metric}.{field}")


def trend_unit(metric: str, field: str) -> str:
    units = {
        ("step_count", "total"): "步",
        ("walking_running_distance", "total"): "km",
        ("apple_exercise_time", "total"): "min",
        ("active_energy", "kcal"): "kcal",
        ("sleep_analysis", "totalSleep"): "hr",
        ("resting_heart_rate", "avg"): "bpm",
        ("heart_rate_variability", "avg"): "ms",
        ("weight_body_mass", "latest"): "kg",
        ("body_fat_percentage", "latest"): "%",
    }
    return units.get((metric, field), "")


def trend_table(trends: dict[str, Any]) -> str:
    rows = []
    for trend in trends.get("metrics", []):
        unit = trend_unit(trend["metric"], trend["field"])
        rows.append([
            trend_label(trend["metric"], trend["field"]),
            trend["days"],
            display_value(trend["avg"], unit),
            display_value(trend["latest"], unit),
            display_value(trend["delta_latest_vs_avg"], unit),
            f"{display_value(trend['min'], unit)} - {display_value(trend['max'], unit)}",
        ])
    rows.append([
        "运动",
        "-",
        f"{trends.get('workout_days', 0)} 天 / {trends.get('workout_count', 0)} 次",
        display_value(trends.get("workout_duration_min"), "min"),
        "-",
        trends.get("period", "-"),
    ])
    return markdown_table(["趋势", "天数", "均值", "最新", "较均值", "范围/周期"], rows)


def deterministic_sections(facts: dict[str, Any], trends: dict[str, Any]) -> str:
    return "\n\n".join([
        "## 数据概览\n\n" + daily_overview_table(facts),
        "## 运动表格\n\n" + workout_table(facts),
        "## 近 7 天趋势\n\n" + trend_table(trends),
    ])


def compact_facts_markdown(facts: dict[str, Any], trends: dict[str, Any]) -> str:
    metrics = facts["metrics"]
    lines = [f"日期: {facts['date']}", f"健康指标数量: {facts['metrics_count']}", ""]
    if facts.get("source"):
        lines.append(f"健康 JSON: {facts['source']}")
        lines.append("")
    lines.append("当日重点健康指标:")
    for name in PRIORITY_METRICS:
        if name in metrics:
            lines.append(metric_line(metrics[name]))
    other_names = [name for name in metrics if name not in PRIORITY_METRICS]
    if other_names:
        lines.append("")
        lines.append("当日其他健康指标:")
        for name in other_names:
            lines.append(metric_line(metrics[name]))

    workouts = facts.get("workouts", {})
    lines.extend(["", "当日运动 JSON 汇总:"])
    lines.append(
        f"- workouts: count={workouts.get('count', 0)}, duration_min={workouts.get('duration_min', 0)}, active_energy_kcal={workouts.get('active_energy_kcal', 0)}"
    )
    for workout in workouts.get("items", []):
        lines.append("- " + ", ".join(f"{key}={format_number(value)}" for key, value in workout.items()))

    lines.extend(["", f"近7天趋势: {trends.get('period', '')}"])
    for trend in trends.get("metrics", []):
        lines.append(
            f"- {trend['metric']}.{trend['field']}: days={trend['days']}, avg={trend['avg']}, min={trend['min']}, max={trend['max']}, latest={trend['latest']}, delta_latest_vs_avg={trend['delta_latest_vs_avg']}"
        )
    lines.append(
        f"- workouts: workout_days={trends.get('workout_days', 0)}, workout_count={trends.get('workout_count', 0)}, workout_duration_min={trends.get('workout_duration_min', 0)}"
    )
    return "\n".join(lines)


def fallback_analysis(facts: dict[str, Any], trends: dict[str, Any]) -> str:
    metrics = facts["metrics"]

    def get(name: str, key: str) -> Any:
        return metrics.get(name, {}).get(key)

    rows = [
        ("步数", get("step_count", "total"), "步"),
        ("步行/跑步距离", get("walking_running_distance", "total"), "km"),
        ("锻炼时间", get("apple_exercise_time", "total"), "min"),
        ("活动能量", get("active_energy", "kcal"), "kcal"),
        ("睡眠", get("sleep_analysis", "totalSleep"), "hr"),
        ("静息心率", get("resting_heart_rate", "avg") or get("resting_heart_rate", "latest"), "次/分"),
        ("HRV", get("heart_rate_variability", "avg"), "ms"),
        ("当日运动", facts.get("workouts", {}).get("count"), "次"),
    ]
    summary_lines = ["## 总结", "", "- AI 未运行或未成功返回，以下是自动指标摘要："]
    for label, value, unit in rows:
        if value is not None:
            summary_lines.append(f"- {label}: {format_number(value)} {unit}")
    advice_lines = [
        "## 建议",
        "",
        "- 优先结合近 7 天睡眠、HRV、活动量判断恢复，而不是只看单日。",
        "- 若运动量增加但睡眠或 HRV 走低，第二天应降低强度。",
        "- 保持固定称重和睡眠记录，用 7 天均值而不是单日波动做判断。",
    ]
    return "\n\n".join(["\n".join(summary_lines), "\n".join(advice_lines)])


def normalize_analysis(text: str) -> str:
    lines = text.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def first_bullets(markdown: str, limit: int) -> list[str]:
    bullets: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped)
            if len(bullets) >= limit:
                break
    return bullets


def section_lines(markdown: str, heading: str) -> list[str]:
    lines = markdown.splitlines()
    capture = False
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            capture = stripped == heading
            continue
        if capture:
            result.append(line)
    return result


def section_bullets(markdown: str, heading: str, limit: int) -> list[str]:
    bullets = []
    for line in section_lines(markdown, heading):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped)
            if len(bullets) >= limit:
                break
    return bullets


def format_ai_frontmatter(analysis: str) -> str:
    normalized = normalize_analysis(analysis)
    summary = section_bullets(normalized, "## 总结", 5)
    suggestions = section_bullets(normalized, "## 建议", 3)
    if not summary:
        bullets = first_bullets(normalized, 8)
        summary = bullets[:5]
        if not suggestions:
            suggestions = bullets[5:8]
    if not summary:
        summary = [line for line in normalized.splitlines() if line.strip() and not line.startswith("#")][:5]
        summary = [f"- {line.strip()}" for line in summary]
    if not suggestions:
        suggestions = ["- 根据数据概览和近 7 天趋势安排今天的活动强度。"]
    return "\n\n".join([
        "## 总结\n\n" + "\n".join(summary),
        "## 建议\n\n" + "\n".join(suggestions[:3]),
    ])


def ai_prompt(facts_md: str) -> str:
    return f"""你是一个谨慎的 Apple 健康与运动数据分析助手。

请基于下面的确定性汇总数据，用中文写一份 Obsidian Markdown 日报。

要求：
- 不要假装知道未提供的数据。
- 综合当日健康 JSON、当日运动 JSON、近 7 天趋势来判断，不要只看单日。
- 只输出两段：`## 总结` 和 `## 建议`。
- `## 总结` 下输出 3-5 条 bullet。
- `## 建议` 下输出 3 条 bullet，建议要具体、保守、可执行。
- 如果数据缺失，明确写出缺失项。
- 不做医疗诊断；涉及异常时建议持续观察或咨询专业人士。
- 直接输出 Markdown 正文，不要包裹代码块。

数据：
{facts_md}
"""


def run_ai(command: str | None, prompt: str, timeout: int) -> tuple[str | None, str | None]:
    resolved = command or os.environ.get("HEALTH_OBSIDIAN_AI_COMMAND")
    if not resolved:
        codex = shutil.which("codex") or "codex"
        resolved = f"{shlex.quote(codex)} exec --ephemeral --skip-git-repo-check --sandbox read-only --model gpt-5.4-mini -"
    try:
        completed = subprocess.run(
            shlex.split(resolved),
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


def render_markdown(
    date: dt.date,
    health_dir: Path,
    workout_dir: Path,
    cache_file: Path,
    facts_md: str,
    analysis: str,
    facts: dict[str, Any],
    trends: dict[str, Any],
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
        "---",
        "",
        f"# {title}",
        "",
    ]
    body = [format_ai_frontmatter(analysis), "", deterministic_sections(facts, trends), ""]
    body.extend([
        "## 同步信息",
        "",
        f"- 健康输入目录: `{health_dir}`",
        f"- 运动输入目录: `{workout_dir}`",
        f"- 本地聚合缓存: `{cache_file}`",
        f"- 生成时间: {dt.datetime.now().isoformat(timespec='seconds')}",
    ])
    if ai_error:
        body.extend(["", "## AI 运行状态", "", f"- AI 未成功返回: `{ai_error[:500]}`"])
    return "\n".join(frontmatter + body).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    date = report_date(args.date)
    health_dir = resolve_health_dir(args)
    workout_dir = resolve_workout_dir(args)
    dates = date_range(date, args.lookback_days)
    note_path = args.output_dir / f"健康日报-{date.isoformat()}.md"
    local_cache = cache_path(args.output_dir, args.cache_file)

    if not health_dir.exists():
        print(f"Missing health JSON directory: {health_dir}", file=sys.stderr)
        return 2
    if note_path.exists() and not args.force and not args.dry_run:
        print(f"Note already exists, use --force to overwrite: {note_path}", file=sys.stderr)
        return 3

    cache = read_cache(local_cache)
    history_by_date = update_cache(cache, health_dir, workout_dir, dates)
    write_cache(local_cache, cache, args.dry_run)
    history = [history_by_date[day.isoformat()] for day in dates]
    facts = history_by_date[date.isoformat()]
    trends = build_trends(history)
    facts_md = compact_facts_markdown(facts, trends)

    ai_error = None
    analysis = None
    if not args.no_ai:
        analysis, ai_error = run_ai(args.ai_command, ai_prompt(facts_md), args.ai_timeout)
    if not analysis:
        analysis = fallback_analysis(facts, trends)

    markdown = render_markdown(date, health_dir, workout_dir, local_cache, facts_md, analysis, facts, trends, ai_error)

    if args.dry_run:
        print(f"Would update cache {local_cache}")
        print(f"Would write {note_path}")
        print(markdown)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    note_path.write_text(markdown, encoding="utf-8")
    print(f"Updated cache {local_cache}")
    print(f"Wrote {note_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
