"""
Output control module for ccb.
Provides quiet mode, debug mode, and JSON output formatting.
"""

import os
import sys
import json
import traceback
from typing import Any, Optional

# Global output state
_quiet_mode = False
_json_mode = False
_debug_mode = False
_output_data = {}
_errors = []


def init_output(quiet: bool = False, json_output: bool = False, debug: bool = False):
    """Initialize output settings from args or environment."""
    global _quiet_mode, _json_mode, _debug_mode, _output_data, _errors
    _quiet_mode = quiet or os.environ.get("CCB_QUIET", "").lower() in ("1", "true", "yes")
    _json_mode = json_output
    _debug_mode = debug or os.environ.get("CCB_DEBUG", "").lower() in ("1", "true", "yes")
    _output_data = {}
    _errors = []


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return _quiet_mode


def is_json() -> bool:
    """Check if JSON output mode is enabled."""
    return _json_mode


def is_debug() -> bool:
    """Check if debug mode is enabled."""
    return _debug_mode


def print_debug(msg: str, *args):
    """Print a debug message if debug mode is enabled."""
    if not _debug_mode:
        return
    if _json_mode:
        if "debug_log" not in _output_data:
            _output_data["debug_log"] = []
        _output_data["debug_log"].append(msg if not args else f"{msg} {' '.join(str(a) for a in args)}")
    else:
        formatted = f"[DEBUG] {msg}" if not args else f"[DEBUG] {msg} {' '.join(str(a) for a in args)}"
        print(formatted, file=sys.stderr)


def print_debug_exception(e: Exception, context: str = ""):
    """Print exception details in debug mode."""
    if not _debug_mode:
        return
    if _json_mode:
        if "debug_log" not in _output_data:
            _output_data["debug_log"] = []
        _output_data["debug_log"].append({
            "context": context,
            "exception": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        })
    else:
        print(f"[DEBUG] {context}: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


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
