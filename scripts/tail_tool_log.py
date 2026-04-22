#!/usr/bin/env python3
"""Pretty-print a Vellum tool-call JSON-line log.

Usage: python scripts/tail_tool_log.py <path-to-log-file>

Streams the file (tail -f style) and prints each line as a colored
summary. Useful when eyeballing an autonomous run to answer: "did the
agent really spawn 3 sub-investigations? how often is it hitting
web_search?".
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


# ANSI colours — degrade to plain text if the terminal doesn't support them.
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"


_TOOL_COLOURS = {
    "upsert_section": _GREEN,
    "update_section_state": _YELLOW,
    "delete_section": _RED,
    "reorder_sections": _BLUE,
    "flag_needs_input": _MAGENTA,
    "flag_decision_point": _MAGENTA,
    "append_reasoning": _DIM,
    "mark_ruled_out": _YELLOW,
    "check_stuck": _RED,
    "request_user_paste": _MAGENTA,
    "web_search": _CYAN,
}


def _format(record: dict) -> str:
    ts = record.get("ts", "?")
    dossier = record.get("dossier_id", "?")
    tool = record.get("tool_name", "?")
    colour = _TOOL_COLOURS.get(tool, _BOLD)
    args = record.get("args_preview")
    result = record.get("result_preview")
    dur = record.get("duration_ms")
    dur_s = f" ({dur}ms)" if dur is not None else ""
    return (
        f"{_DIM}{ts}{_RESET} "
        f"[{_DIM}{dossier}{_RESET}] "
        f"{colour}{tool}{_RESET}{dur_s}\n"
        f"    args:   {json.dumps(args, default=str)}\n"
        f"    result: {json.dumps(result, default=str)}"
    )


def _follow(path: Path):
    """Yield lines as they are appended to the file. Blocks between writes."""
    with path.open("r", encoding="utf-8") as fh:
        # Print everything already in the file first.
        for line in fh:
            yield line
        # Then tail.
        while True:
            line = fh.readline()
            if not line:
                time.sleep(0.25)
                continue
            yield line


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: tail_tool_log.py <path-to-log-file>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"log file does not exist: {path}", file=sys.stderr)
        return 1

    try:
        for line in _follow(path):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"{_DIM}[non-json] {line}{_RESET}")
                continue
            print(_format(record))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
