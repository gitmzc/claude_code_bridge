"""
Output control module for ccb.
Provides quiet mode, debug mode, JSON output formatting, and atomic file writes.
Also provides TTY-aware output degradation for emoji and spinner characters.
"""

import os
import sys
import json
import tempfile
import traceback
from pathlib import Path
from typing import Any, Optional, Union

# Global output state
_quiet_mode = False
_json_mode = False
_debug_mode = False
_output_data = {}
_errors = []

# Emoji to text fallback mapping
_EMOJI_FALLBACK = {
    "✅": "[OK]",
    "❌": "[ERROR]",
    "⚠️": "[WARN]",
    "📊": "[STATUS]",
    "🔔": "[INFO]",
    "🤖": "[AI]",
    "🚀": "[START]",
    "⏰": "[TIMEOUT]",
    "⏳": "[WAIT]",
    "✨": "[NEW]",
    "📦": "[UPDATE]",
    "🔄": "[SYNC]",
    "🔧": "[FIX]",
    "ℹ️": "[INFO]",
}

# Spinner characters for TTY vs non-TTY
_SPINNER_TTY = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_PLAIN = "-\\|/"


def is_tty() -> bool:
    """Check if stdout is a TTY (interactive terminal)."""
    return sys.stdout.isatty() and not _json_mode


def emoji(char: str, fallback: Optional[str] = None) -> str:
    """Return emoji if TTY, otherwise return text fallback.

    Args:
        char: The emoji character
        fallback: Optional custom fallback text. If not provided, uses default mapping.

    Returns:
        The emoji if in TTY mode, otherwise the fallback text.
    """
    if is_tty():
        return char
    if fallback is not None:
        return fallback
    return _EMOJI_FALLBACK.get(char, char)


def spinner_chars() -> str:
    """Return appropriate spinner characters for current environment."""
    return _SPINNER_TTY if is_tty() else _SPINNER_PLAIN


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


def atomic_write(file_path: Union[str, Path], content: str, encoding: str = "utf-8") -> bool:
    """Write content to file atomically using temp file + rename.

    This prevents partial writes and ensures the file is either fully written
    or not modified at all. Safe for concurrent access.

    Args:
        file_path: Target file path
        content: Content to write
        encoding: File encoding (default: utf-8)

    Returns:
        True if successful, False otherwise
    """
    target = Path(file_path)
    target_dir = target.parent

    try:
        # Ensure parent directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory (for atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir,
            prefix=f".{target.name}.",
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename (works on POSIX, best-effort on Windows)
            os.replace(tmp_path, target)
            return True
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print_debug(f"atomic_write failed for {file_path}: {e}")
        return False


def atomic_write_json(file_path: Union[str, Path], data: Any, indent: int = 2) -> bool:
    """Write JSON data to file atomically.

    Args:
        file_path: Target file path
        data: Data to serialize as JSON
        indent: JSON indentation (default: 2)

    Returns:
        True if successful, False otherwise
    """
    try:
        content = json.dumps(data, ensure_ascii=False, indent=indent)
        return atomic_write(file_path, content)
    except (TypeError, ValueError) as e:
        print_debug(f"atomic_write_json serialization failed: {e}")
        return False
