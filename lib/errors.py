"""
Error codes and diagnostic messages for ccb CLI.

Exit codes follow Unix conventions:
- 0: Success
- 1: General error
- 2: Command line usage error
- 10-19: Configuration errors
- 20-29: Session/runtime errors
- 30-39: Network/external service errors
- 40-49: Terminal/backend errors
"""

from enum import IntEnum
from typing import Optional, Dict


class ExitCode(IntEnum):
    """Exit codes for ccb CLI."""

    # Success
    SUCCESS = 0

    # General errors (1-9)
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    INTERRUPTED = 3

    # Configuration errors (10-19)
    CONFIG_NOT_FOUND = 10
    CONFIG_INVALID = 11
    CONFIG_PERMISSION = 12
    MISSING_DEPENDENCY = 13

    # Session/runtime errors (20-29)
    SESSION_NOT_FOUND = 20
    SESSION_ALREADY_EXISTS = 21
    SESSION_INVALID = 22
    SESSION_WRITE_ERROR = 23
    NO_RECOVERABLE_HISTORY = 24

    # Network/external service errors (30-39)
    NETWORK_ERROR = 30
    API_ERROR = 31
    UPDATE_FAILED = 32

    # Terminal/backend errors (40-49)
    TERMINAL_NOT_DETECTED = 40
    TERMINAL_NOT_SUPPORTED = 41
    BACKEND_START_FAILED = 42
    BACKEND_NOT_RUNNING = 43
    PANE_CREATE_FAILED = 44


# Error messages with resolution suggestions
ERROR_INFO: Dict[ExitCode, Dict[str, str]] = {
    ExitCode.SUCCESS: {
        "message": "Operation completed successfully",
        "suggestion": "",
    },
    ExitCode.GENERAL_ERROR: {
        "message": "An unexpected error occurred",
        "suggestion": "Run 'ccb doctor' to diagnose issues, or use --debug for more details",
    },
    ExitCode.USAGE_ERROR: {
        "message": "Invalid command or arguments",
        "suggestion": "Run 'ccb --help' for usage information",
    },
    ExitCode.INTERRUPTED: {
        "message": "Operation was interrupted",
        "suggestion": "Run the command again to retry",
    },
    ExitCode.CONFIG_NOT_FOUND: {
        "message": "Configuration file not found",
        "suggestion": "Run 'ccb init' to create a configuration file",
    },
    ExitCode.CONFIG_INVALID: {
        "message": "Configuration file is invalid or corrupted",
        "suggestion": "Check the JSON syntax in .ccb-config.json or run 'ccb init' to recreate",
    },
    ExitCode.CONFIG_PERMISSION: {
        "message": "Cannot read or write configuration file",
        "suggestion": "Check file permissions for .ccb-config.json",
    },
    ExitCode.MISSING_DEPENDENCY: {
        "message": "Required dependency is missing",
        "suggestion": "Run 'ccb doctor' to check dependencies and install missing ones",
    },
    ExitCode.SESSION_NOT_FOUND: {
        "message": "Session file not found",
        "suggestion": "Start a new session with 'ccb up <provider>'",
    },
    ExitCode.SESSION_ALREADY_EXISTS: {
        "message": "Session already exists and is running",
        "suggestion": "Use 'ccb restore' to attach, or 'ccb kill' to terminate first",
    },
    ExitCode.SESSION_INVALID: {
        "message": "Session file is invalid or corrupted",
        "suggestion": "Delete the .<provider>-session file and start a new session",
    },
    ExitCode.SESSION_WRITE_ERROR: {
        "message": "Cannot write session file",
        "suggestion": "Check write permissions in the current directory",
    },
    ExitCode.NO_RECOVERABLE_HISTORY: {
        "message": "No recoverable session history found",
        "suggestion": "Start a fresh session with 'ccb up <provider>'",
    },
    ExitCode.NETWORK_ERROR: {
        "message": "Network connection failed",
        "suggestion": "Check your internet connection and try again",
    },
    ExitCode.API_ERROR: {
        "message": "API request failed",
        "suggestion": "Check API credentials and service status",
    },
    ExitCode.UPDATE_FAILED: {
        "message": "Failed to update ccb",
        "suggestion": "Try manual update: cd ~/.local/share/codex-dual && git pull",
    },
    ExitCode.TERMINAL_NOT_DETECTED: {
        "message": "Could not detect terminal environment",
        "suggestion": "Run 'ccb init' to configure terminal manually, or set CCB_BACKEND_ENV",
    },
    ExitCode.TERMINAL_NOT_SUPPORTED: {
        "message": "Terminal is not supported",
        "suggestion": "ccb supports WezTerm and iTerm2. Install one of these terminals.",
    },
    ExitCode.BACKEND_START_FAILED: {
        "message": "Failed to start AI backend",
        "suggestion": "Check that the AI CLI (codex/gemini) is installed and configured",
    },
    ExitCode.BACKEND_NOT_RUNNING: {
        "message": "AI backend is not running",
        "suggestion": "Start the backend with 'ccb up <provider>'",
    },
    ExitCode.PANE_CREATE_FAILED: {
        "message": "Failed to create terminal pane",
        "suggestion": "Check terminal configuration and permissions",
    },
}


def get_error_message(code: ExitCode) -> str:
    """Get the error message for an exit code."""
    info = ERROR_INFO.get(code, ERROR_INFO[ExitCode.GENERAL_ERROR])
    return info["message"]


def get_error_suggestion(code: ExitCode) -> str:
    """Get the resolution suggestion for an exit code."""
    info = ERROR_INFO.get(code, ERROR_INFO[ExitCode.GENERAL_ERROR])
    return info["suggestion"]


def format_error(code: ExitCode, detail: Optional[str] = None) -> str:
    """Format a complete error message with suggestion.

    Args:
        code: The exit code
        detail: Optional additional detail about the error

    Returns:
        Formatted error string
    """
    info = ERROR_INFO.get(code, ERROR_INFO[ExitCode.GENERAL_ERROR])
    parts = [f"Error [{code.value}]: {info['message']}"]

    if detail:
        parts.append(f"  Detail: {detail}")

    if info["suggestion"]:
        parts.append(f"  Suggestion: {info['suggestion']}")

    return "\n".join(parts)


def print_error_and_exit(code: ExitCode, detail: Optional[str] = None) -> int:
    """Print formatted error and return exit code.

    This function is designed to be used with sys.exit():
        sys.exit(print_error_and_exit(ExitCode.CONFIG_NOT_FOUND))

    Args:
        code: The exit code
        detail: Optional additional detail

    Returns:
        The exit code value (for use with sys.exit)
    """
    import sys
    from output import is_json, print_error as output_error, set_output, flush_json

    if is_json():
        set_output("error_code", code.value)
        set_output("error_name", code.name)
        set_output("error_message", get_error_message(code))
        set_output("error_suggestion", get_error_suggestion(code))
        if detail:
            set_output("error_detail", detail)
        return flush_json(code.value)
    else:
        output_error(format_error(code, detail))
        return code.value
