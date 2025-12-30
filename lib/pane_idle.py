"""
Pane Idle Detection - Wait for terminal pane to become idle before sending messages.

Inspired by CCCC project's PaneIdleJudge implementation.
This helps avoid interrupting AI while it's still outputting content.
"""
from __future__ import annotations
import os
import re
import subprocess
import time
from typing import Tuple, Optional

# Strip ANSI escape sequences for content comparison
ANSI_RE = re.compile(r"\x1b\[.*?m|\x1b\[?[\d;]*[A-Za-z]")


def _env_float(name: str, default: float) -> float:
    """Get float from environment variable with default."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class PaneIdleJudge:
    """Detect if a terminal pane is idle based on screen content stability.

    This is NOT a precise idle detector - it only checks if the pane content
    has been stable for `quiet_seconds`. Use as a basic throttling mechanism
    to avoid interrupting AI output.
    """

    def __init__(self, quiet_seconds: float = 1.5):
        """
        Args:
            quiet_seconds: Screen must be stable for this many seconds to be considered idle.
                          Can be overridden by CCB_IDLE_QUIET_SEC environment variable.
        """
        self.quiet_sec = _env_float("CCB_IDLE_QUIET_SEC", quiet_seconds)
        self._last_snapshot = ""
        self._last_change_ts = 0.0

    def capture_pane_wezterm(self, pane_id: str, lines: int = 500) -> str:
        """Capture pane content from WezTerm."""
        try:
            result = subprocess.run(
                ["wezterm", "cli", "get-text", "--pane-id", pane_id, "--start-line", f"-{lines}"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                return ANSI_RE.sub("", result.stdout)
        except Exception:
            pass
        return ""

    def capture_pane_iterm2(self, session_id: str, lines: int = 500) -> str:
        """Capture pane content from iTerm2 using AppleScript."""
        try:
            # iTerm2 doesn't have a direct CLI for capturing text
            # We use AppleScript as a fallback
            script = f'''
            tell application "iTerm2"
                tell current window
                    tell current session
                        set theText to text
                        return theText
                    end tell
                end tell
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                # Only return last N lines
                all_lines = result.stdout.splitlines()
                return "\n".join(all_lines[-lines:])
        except Exception:
            pass
        return ""

    def capture_pane(self, pane_id: str, terminal: str = "wezterm", lines: int = 500) -> str:
        """Capture pane content based on terminal type."""
        if terminal == "wezterm":
            return self.capture_pane_wezterm(pane_id, lines)
        elif terminal == "iterm2":
            return self.capture_pane_iterm2(pane_id, lines)
        else:
            # Unknown terminal, return empty (will be treated as idle)
            return ""

    def is_idle(self, pane_id: str, terminal: str = "wezterm") -> Tuple[bool, str]:
        """Check if pane is idle (content stable for quiet_sec seconds).

        Args:
            pane_id: Terminal pane ID
            terminal: Terminal type ("wezterm" or "iterm2")

        Returns:
            (is_idle, reason) - reason is "quiet" if idle, "changing" if not
        """
        text = self.capture_pane(pane_id, terminal)
        now = time.time()

        if text != self._last_snapshot:
            self._last_snapshot = text
            self._last_change_ts = now

        if now - self._last_change_ts >= self.quiet_sec:
            return True, "quiet"

        return False, "changing"

    def wait_for_idle(
        self,
        pane_id: str,
        terminal: str = "wezterm",
        timeout: float = 6.0,
        interval: float = 0.5,
    ) -> Tuple[bool, float]:
        """Wait for pane to become idle.

        Args:
            pane_id: Terminal pane ID
            terminal: Terminal type ("wezterm" or "iterm2")
            timeout: Maximum wait time in seconds.
                    Can be overridden by CCB_IDLE_TIMEOUT environment variable.
            interval: Check interval in seconds

        Returns:
            (became_idle, waited_seconds) - became_idle is True if pane became idle
        """
        timeout = _env_float("CCB_IDLE_TIMEOUT", timeout)
        t0 = time.time()

        while True:
            elapsed = time.time() - t0
            if elapsed >= timeout:
                return False, elapsed

            idle, _ = self.is_idle(pane_id, terminal)
            if idle:
                return True, elapsed

            time.sleep(interval)


def should_skip_idle_check() -> bool:
    """Check if idle detection should be skipped (via environment variable)."""
    return os.environ.get("CCB_SKIP_IDLE_CHECK", "").lower() in ("1", "true", "yes")


def wait_for_pane_idle(
    pane_id: str,
    terminal: str = "wezterm",
    quiet_seconds: float = 1.5,
    timeout: float = 6.0,
) -> Tuple[bool, float]:
    """Convenience function to wait for pane to become idle.

    Args:
        pane_id: Terminal pane ID
        terminal: Terminal type ("wezterm" or "iterm2")
        quiet_seconds: Screen must be stable for this many seconds
        timeout: Maximum wait time

    Returns:
        (became_idle, waited_seconds)
    """
    if should_skip_idle_check():
        return True, 0.0

    judge = PaneIdleJudge(quiet_seconds=quiet_seconds)
    return judge.wait_for_idle(pane_id, terminal, timeout)
