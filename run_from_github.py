#!/usr/bin/env python3
"""
run_from_github.py

Fetches the latest movieradar.py straight from GitHub (raw file, no git
required on the host) and runs it. Same pattern as pulling a live config
from raw.githubusercontent.com at runtime -- here it's the code itself
that's fetched fresh each run instead of a local checkout being updated.

config.json (your real API keys) lives locally next to this launcher and is
never fetched from GitHub -- only movieradar.py is.

Point Task Scheduler / cron at:
    python3 /path/to/run_from_github.py
"""

import os
import subprocess
import sys
import urllib.request

RAW_URL = "https://raw.githubusercontent.com/gerardcm/movieradar/main/movieradar.py"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FETCHED_SCRIPT = os.path.join(SCRIPT_DIR, "_movieradar_fetched.py")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def fetch_latest():
    req = urllib.request.Request(RAW_URL, headers={"User-Agent": "movieradar-launcher"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        code = resp.read()
    if not code.strip():
        sys.exit(f"Fetched empty file from {RAW_URL} -- aborting rather than running nothing.")
    with open(FETCHED_SCRIPT, "wb") as f:
        f.write(code)


def main():
    if not os.path.exists(CONFIG_PATH):
        sys.exit(
            f"config.json not found at {CONFIG_PATH}.\n"
            "Copy config.example.json to config.json in this same folder and "
            "fill in your API keys first."
        )

    print(f"Fetching latest movieradar.py from {RAW_URL} ...")
    fetch_latest()

    print("Running movieradar...")
    result = subprocess.run(
        [sys.executable, FETCHED_SCRIPT, "--config", CONFIG_PATH]
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
