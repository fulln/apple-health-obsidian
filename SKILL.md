---
name: apple-health-obsidian
description: Generate daily Apple Health and activity summaries from Health Auto Export JSON files into an Obsidian vault. Use when Codex needs to sync `/Users/fulln/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/data` JSON exports, analyze yesterday's Apple Health, exercise, sleep, heart, energy, walking, and body metrics with AI, create Markdown notes under `life/body/`, or install/update the local launchd schedule for this workflow.
---

# Apple Health Obsidian

Use the bundled scripts to turn Health Auto Export JSON files into daily Obsidian notes.

## Default Paths

- Health source: `/Users/fulln/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/data`
- Obsidian vault: `/Users/fulln/opt/TIL`
- Output folder: `/Users/fulln/opt/TIL/life/body`
- JSON archive: `/Users/fulln/opt/TIL/life/body/health-json`
- LaunchAgent label: `com.fulln.apple-health-obsidian`

## Generate A Report

Run:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py
```

By default this analyzes yesterday, syncs all matching `HealthAutoExport-*.json` files into the archive, and writes `健康日报-YYYY-MM-DD.md` under `life/body/`.

Useful options:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py --date 2026-04-21
/usr/bin/python3 scripts/health_obsidian_report.py --no-ai
/usr/bin/python3 scripts/health_obsidian_report.py --dry-run
/usr/bin/python3 scripts/health_obsidian_report.py --output-dir /path/to/vault/life/body
```

## AI Summary

The report script first computes deterministic facts from JSON, then asks AI to write the Chinese narrative summary.

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

The installer defaults the scheduled job to `/usr/local/bin/python3` when it exists. On this Mac, `/usr/bin/python3` was blocked from reading the iCloud `Mobile Documents` export path under launchd.

## Metric Notes

Read `references/health-auto-export.md` when updating parsing logic or adding new metrics.
