"""
Output control module for ccb.
Provides quiet mode and JSON output formatting.
"""

import os
import sys
import json
from typing import Any, Optional

# Global output state
_quiet_mode = False
_json_mode = False
_output_data = {}
_errors = []


def init_output(quiet: bool = False, json_output: bool = False):
    """Initialize output settings from args or environment."""
    global _quiet_mode, _json_mode, _output_data, _errors
    _quiet_mode = quiet or os.environ.get("CCB_QUIET", "").lower() in ("1", "true", "yes")
    _json_mode = json_output
    _output_data = {}
    _errors = []


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return _quiet_mode


def is_json() -> bool:
    """Check if JSON output mode is enabled."""
    return _json_mode


def print_msg(msg: str, force: bool = False):
    """Print a message unless in quiet mode."""
    if _json_mode:
        return  # Suppress text output in JSON mode
    if not _quiet_mode or force:
        print(msg)


def print_error(msg: str):
    """Print an error message (always shown, even in quiet mode)."""
    if _json_mode:
        _errors.append(msg)
    else:
        print(msg, file=sys.stderr)


def set_output(key: str, value: Any):
    """Set a key-value pair for JSON output."""
    _output_data[key] = value


def add_to_list(key: str, value: Any):
    """Add a value to a list in the output data."""
    if key not in _output_data:
        _output_data[key] = []
    _output_data[key].append(value)


def get_output() -> dict:
    """Get the current output data."""
    return _output_data.copy()


def flush_json(exit_code: int = 0) -> int:
    """Print JSON output and return exit code."""
    if _json_mode:
        _output_data["success"] = exit_code == 0
        _output_data["exit_code"] = exit_code
        if _errors:
            _output_data["errors"] = _errors
        print(json.dumps(_output_data, ensure_ascii=False, indent=2))
    return exit_code
