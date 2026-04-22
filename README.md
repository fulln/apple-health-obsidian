# Apple Health Obsidian

Generate daily Apple Health summaries from Health Auto Export data and write them into an Obsidian vault.

The script normalizes raw health/workout exports into compact daily facts first, then asks AI for a short summary and recommendations. Tables in the Markdown note are generated deterministically by the script.

## Output

The generated note is structured as:

1. `总结`
2. `建议`
3. `数据概览`
4. `运动表格`
5. `近 7 天趋势`
6. `同步信息`

## Default Paths

All defaults are based on the current macOS user:

| Purpose | Path |
| --- | --- |
| Health JSON | `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/health` |
| Workout JSON | `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/workout` |
| AutoSync fallback | `$HOME/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/AutoSync` |
| Obsidian output | `$HOME/opt/TIL/life/body` |
| Local aggregate cache | `$HOME/opt/TIL/life/body/.apple-health-cache/daily-facts.json` |
| launchd logs | `$HOME/Library/Logs/apple-health-obsidian` |

## Usage

Generate yesterday's report:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py
```

Generate a specific date:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py --date 2026-04-21
```

Preview without writing:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py --dry-run --no-ai
```

Use custom folders:

```bash
/usr/bin/python3 scripts/health_obsidian_report.py \
  --health-dir "$HOME/path/to/health" \
  --workout-dir "$HOME/path/to/workout" \
  --output-dir "$HOME/path/to/vault/life/body"
```

## AI

By default the script calls:

```bash
codex exec --ephemeral --skip-git-repo-check --sandbox read-only --model gpt-5.4-mini -
```

Override the AI command:

```bash
HEALTH_OBSIDIAN_AI_COMMAND='claude -p' /usr/bin/python3 scripts/health_obsidian_report.py
```

If AI fails or times out, the script still writes a fallback note using deterministic metrics.

## Schedule

Install or refresh the daily launchd job:

```bash
/usr/bin/python3 scripts/install_launchd.py --load
```

Default schedule: daily at `08:10`.

Change the schedule:

```bash
/usr/bin/python3 scripts/install_launchd.py --load --hour 7 --minute 30
```

Trigger immediately after loading:

```bash
/usr/bin/python3 scripts/install_launchd.py --load --run-now
```

## Data Handling

- Raw JSON is not archived or copied.
- The local cache stores normalized daily aggregates only.
- AI receives compact facts and trends, not raw per-sample health arrays.

## Development

Run tests:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```
