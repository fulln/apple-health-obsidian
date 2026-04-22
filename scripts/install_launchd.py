#!/usr/bin/env python3
"""Install a launchd job for the Apple Health Obsidian report."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.fulln.apple-health-obsidian"
SCRIPT = Path(__file__).resolve().parent / "health_obsidian_report.py"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "apple-health-obsidian"
DEFAULT_PATH_PARTS = [
    "/usr/local/opt/nvm/versions/node/v24.15.0/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
]
DEFAULT_RUNTIME_PYTHON = (
    "/usr/local/bin/python3" if Path("/usr/local/bin/python3").exists() else sys.executable
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hour", type=int, default=8)
    parser.add_argument("--minute", type=int, default=10)
    parser.add_argument("--load", action="store_true", help="Load or reload the LaunchAgent.")
    parser.add_argument("--run-now", action="store_true", help="Kickstart the job after loading.")
    parser.add_argument("--python", default=DEFAULT_RUNTIME_PYTHON)
    parser.add_argument("--extra-arg", action="append", default=[], help="Extra report argument.")
    return parser.parse_args()


def plist_payload(args: argparse.Namespace) -> dict[str, object]:
    program_arguments = [args.python, str(SCRIPT), "--force"]
    program_arguments.extend(args.extra_arg)
    path_parts = []
    for part in os.environ.get("PATH", "").split(":") + DEFAULT_PATH_PARTS:
        if part and part not in path_parts:
            path_parts.append(part)
    return {
        "Label": LABEL,
        "ProgramArguments": program_arguments,
        "StartCalendarInterval": {"Hour": args.hour, "Minute": args.minute},
        "StandardOutPath": str(LOG_DIR / "stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "stderr.log"),
        "WorkingDirectory": str(SCRIPT.parent.parent),
        "RunAtLoad": False,
        "EnvironmentVariables": {
            "PATH": ":".join(path_parts),
        },
    }


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(f"{' '.join(command)} failed: {detail}")


def main() -> int:
    args = parse_args()
    if not 0 <= args.hour <= 23:
        raise SystemExit("--hour must be 0..23")
    if not 0 <= args.minute <= 59:
        raise SystemExit("--minute must be 0..59")

    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with PLIST.open("wb") as handle:
        plistlib.dump(plist_payload(args), handle, sort_keys=False)
    print(f"Wrote {PLIST}")

    if args.load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(PLIST)], capture_output=True, text=True)
        run(["launchctl", "bootstrap", domain, str(PLIST)])
        run(["launchctl", "enable", f"{domain}/{LABEL}"])
        print(f"Loaded {LABEL}")
        if args.run_now:
            run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])
            print(f"Started {LABEL}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
