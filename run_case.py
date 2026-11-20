#!/usr/bin/env python3
"""Entry script for selecting and executing pytest cases.

Author: Kawhi.He
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ALIASES = {
    "linkeda": "linke",
    "linke": "linke",
    "aima": "aima",
}


def now_text() -> str:
    """Return current time as text.

    Args:
        None.

    Returns:
        str: Current local timestamp in YYYY-mm-dd HH:MM:SS format.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_project(project: str) -> str:
    """Normalize project name to an internal key.

    Args:
        project: Original project value from runner task/config.

    Returns:
        str: Normalized project key.
    """
    key = (project or "").strip().lower()
    return PROJECT_ALIASES.get(key, key)


def load_case_map(case_map_path: Path) -> Dict[str, Dict[str, str]]:
    """Load case-nodeid mapping from a JSON file.

    Args:
        case_map_path: Mapping file path.

    Returns:
        dict: Mapping dictionary with top-level key "projects".
    """
    if not case_map_path.is_file():
        raise SystemExit(f"case map file not found: {case_map_path}")
    with case_map_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        raise SystemExit("invalid case-map.json: missing 'projects' object")
    return projects


def build_pytest_args(
    args: argparse.Namespace,
    case_map: Dict[str, Dict[str, str]],
) -> List[str]:
    """Build pytest CLI arguments from the current task metadata.

    Args:
        args: Parsed command arguments.
        case_map: Project-case mapping loaded from JSON.

    Returns:
        list[str]: Full pytest argument list.
    """
    project_key = normalize_project(args.project)
    project_cases = case_map.get(project_key, {})

    target: Optional[str] = None
    case_no = (args.case_no or "").strip()
    if case_no:
        target = project_cases.get(case_no)
        if not target:
            available = ", ".join(sorted(project_cases.keys())) or "<none>"
            raise SystemExit(
                "case_no '%s' not configured for project '%s', available: %s"
                % (case_no, project_key, available)
            )
    else:
        target = f"tests/projects/{project_key}"

    return [
        "-s",
        "-q",
        target,
        "--tb=short",
        "--maxfail=1",
        f"--project={project_key}",
        f"--case-no={case_no}",
        f"--case-name={args.case_name or ''}",
        f"--base-id={args.base_id or ''}",
    ]


def stream_process(command: List[str], log_file: Path) -> int:
    """Run a subprocess and stream output to terminal and log file.

    Args:
        command: Executable command list.
        log_file: Output log file path.

    Returns:
        int: Process exit code.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"[{now_text()}] command: {' '.join(command)}\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            handle.write(line)
        return process.wait()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        None.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run mapped pytest case by task metadata."
    )
    parser.add_argument(
        "--project", default="linkeda", help="Project key from runner task"
    )
    parser.add_argument(
        "--case-no", default="", help="Case number from runner task"
    )
    parser.add_argument(
        "--case-name", default="", help="Case name from runner task"
    )
    parser.add_argument(
        "--base-id", default="", help="Base ID from runner task"
    )
    parser.add_argument(
        "--case-map", default="case-map.json", help="Case map file path"
    )
    parser.add_argument(
        "--log-dir", default="logs", help="Directory for local pytest logs"
    )
    return parser.parse_args()


def main() -> int:
    """Program entry to run pytest for the selected case.

    Args:
        None.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    case_map = load_case_map(Path(args.case_map))
    pytest_args = build_pytest_args(args, case_map)

    run_name = (args.case_no or "all").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_dir) / (
        f"{normalize_project(args.project)}_{run_name}_{timestamp}.log"
    )

    command = [sys.executable, "-m", "pytest", *pytest_args]
    print(f"[{now_text()}] start pytest run")
    print(f"[{now_text()}] log file: {log_file}")
    exit_code = stream_process(command, log_file)
    print(f"[{now_text()}] pytest exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
