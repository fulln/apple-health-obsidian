---
name: apple-health-obsidian
description: Generate daily Apple Health and workout summaries from Health Auto Export JSON or AutoSync files into an Obsidian vault. Use when Codex needs to read `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/health`, `/workout`, or AutoSync HealthMetrics/Workouts, normalize health and workout data into compact local aggregates, analyze yesterday plus the previous 7 days with AI, create Markdown notes under `life/body/`, or install/update the local launchd schedule.
---

# Apple Health Obsidian

Use the bundled scripts to normalize Health Auto Export data into compact daily facts, then write AI-assisted Obsidian notes.

## Default Paths

- Health JSON source: `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/health`
- Workout JSON source: `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/workout`
- AutoSync fallback: `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/AutoSync`
- Output folder: prefer explicit `--output-dir /path/to/vault/life/body`; otherwise infer from a detectable local Obsidian vault.
- Local aggregate cache: defaults to `<output-dir>/.apple-health-cache/daily-facts.json`; override with `--cache-file`.
- LaunchAgent label: `com.fulln.apple-health-obsidian`

## Generate A Report

Run:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py --output-dir /path/to/vault/life/body
```

By default this analyzes yesterday, updates the compact aggregate cache for the previous 7 days, and writes `健康日报-YYYY-MM-DD.md` under the selected output folder. It does not archive or copy raw JSON.

Useful options:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py --date 2026-04-21
/usr/bin/python3 scripts/health_obsidian_report.py --no-ai
/usr/bin/python3 scripts/health_obsidian_report.py --dry-run
/usr/bin/python3 scripts/health_obsidian_report.py --health-dir /path/to/health --workout-dir /path/to/workout
/usr/bin/python3 scripts/health_obsidian_report.py --output-dir /path/to/vault/life/body
```

## AI Summary

The report script first computes deterministic facts from health/workout JSON or AutoSync data, writes only normalized aggregates to the local cache, then asks AI to write the Chinese summary and recommendations.

Default AI command:

```bash
codex exec --ephemeral --skip-git-repo-check --sandbox read-only --model gpt-5.4-mini -
```

Override it with:

```bash
HEALTH_OBSIDIAN_AI_COMMAND='claude -p' /usr/bin/python3 scripts/health_obsidian_report.py
```

If the AI command fails or times out, the script still writes a metrics-only Markdown report and records the AI error in the note.

## Install The Schedule

Install or refresh the local launchd job:

```bash
/usr/bin/python3 scripts/install_launchd.py --load
```

The default schedule runs daily at 08:10 local time. Change it with:

```bash
/usr/bin/python3 scripts/install_launchd.py --load --hour 7 --minute 30
```

Logs go to `~/Library/Logs/apple-health-obsidian/`.

## Metric Notes

Read `references/health-auto-export.md` when updating parsing logic or adding new metrics.
