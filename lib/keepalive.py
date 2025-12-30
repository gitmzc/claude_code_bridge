"""
Keepalive Mechanism - Auto-remind AI to continue when it declares "Next:" but stalls.

Inspired by CCCC project's keepalive implementation.
When AI declares "Next: xxx" but stops responding, send a reminder after delay.
"""
from __future__ import annotations
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Callable, List


def _env_float(name: str, default: float) -> float:
    """Get float from environment variable with default."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    """Get bool from environment variable."""
    val = os.environ.get(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


@dataclass
class PendingKeepalive:
    """Pending keepalive entry."""
    due: float          # Timestamp when keepalive should be sent
    next_hint: str      # Content after "Next:" declaration
    provider: str       # "codex" or "gemini"


class Keepalive:
    """Keepalive mechanism: detect "Next:" declarations and send reminders.

    When AI declares "Next: xxx" but stops responding, this mechanism
    sends a reminder after a configurable delay.

    Usage:
        keepalive = Keepalive(delay_seconds=60)

        # When receiving AI message
        keepalive.on_message("codex", ai_reply)

        # Periodically check and send keepalives
        keepalive.tick(send_fn, is_busy_fn)
    """

    # Match "Next:" or "- Next:" or "* Next:" patterns
    NEXT_RE = re.compile(r"(?mi)^\s*(?:[-*]\s*)?Next\s*(?:\(|:)\s*(.+)$")

    def __init__(self, delay_seconds: float = 60.0, enabled: bool = True):
        """
        Args:
            delay_seconds: Seconds to wait after "Next:" before sending keepalive.
                          Can be overridden by CCB_KEEPALIVE_DELAY environment variable.
            enabled: Whether keepalive is enabled.
                    Can be overridden by CCB_KEEPALIVE_ENABLED environment variable.
        """
        self.delay = _env_float("CCB_KEEPALIVE_DELAY", delay_seconds)
        self.enabled = _env_bool("CCB_KEEPALIVE_ENABLED", enabled)
        self.pending: Dict[str, Optional[PendingKeepalive]] = {}

    def _extract_next(self, message: str) -> str:
        """Extract the first "Next:" declaration from message.

        Returns:
            Content after "Next:" or empty string if not found.
        """
        match = self.NEXT_RE.search(message)
        if match:
            return match.group(1).strip()
        return ""

    def on_message(self, provider: str, message: str) -> None:
        """Process AI message and schedule keepalive if "Next:" is declared.

        Args:
            provider: "codex" or "gemini"
            message: AI's reply content
        """
        if not self.enabled:
            return

        if provider not in ("codex", "gemini"):
            return

        next_hint = self._extract_next(message)
        if next_hint:
            self.pending[provider] = PendingKeepalive(
                due=time.time() + self.delay,
                next_hint=next_hint,
                provider=provider
            )
        else:
            # No "Next:" declaration, cancel any pending keepalive
            self.pending[provider] = None

    def tick(
        self,
        send_fn: Callable[[str, str], None],
        is_busy_fn: Optional[Callable[[str], bool]] = None
    ) -> List[str]:
        """Check and send due keepalives.

        Args:
            send_fn: Function to send message (provider, message) -> None
            is_busy_fn: Optional function to check if provider is busy (provider) -> bool
                       If busy, skip sending and cancel the pending keepalive.

        Returns:
            List of providers that received keepalive messages.
        """
        if not self.enabled:
            return []

        sent_to = []
        now = time.time()

        for provider in list(self.pending.keys()):
            pending = self.pending.get(provider)
            if pending is None:
                continue

            # Not due yet
            if now < pending.due:
                continue

            # Check if busy (skip if busy)
            if is_busy_fn and is_busy_fn(provider):
                self.pending[provider] = None
                continue

            # Build and send keepalive message
            if pending.next_hint:
                msg = f"[KEEPALIVE] Continue: {pending.next_hint}"
            else:
                msg = "[KEEPALIVE] Continue your work."

            try:
                send_fn(provider, msg)
                sent_to.append(provider)
            except Exception:
                pass

            # Clear pending (one keepalive per "Next:" declaration)
            self.pending[provider] = None

        return sent_to

    def cancel(self, provider: str) -> None:
        """Cancel pending keepalive for a provider."""
        self.pending[provider] = None

    def cancel_all(self) -> None:
        """Cancel all pending keepalives."""
        self.pending.clear()

    def get_pending(self, provider: str) -> Optional[PendingKeepalive]:
        """Get pending keepalive for a provider (for debugging/testing)."""
        return self.pending.get(provider)

    def time_until_due(self, provider: str) -> Optional[float]:
        """Get seconds until keepalive is due for a provider.

        Returns:
            Seconds until due, or None if no pending keepalive.
            Negative value means overdue.
        """
        pending = self.pending.get(provider)
        if pending is None:
            return None
        return pending.due - time.time()


# Global instance for convenience
_global_keepalive: Optional[Keepalive] = None


def get_keepalive() -> Keepalive:
    """Get or create global Keepalive instance."""
    global _global_keepalive
    if _global_keepalive is None:
        _global_keepalive = Keepalive()
    return _global_keepalive


def on_ai_message(provider: str, message: str) -> None:
    """Convenience function to process AI message with global keepalive."""
    get_keepalive().on_message(provider, message)


def tick_keepalive(
    send_fn: Callable[[str, str], None],
    is_busy_fn: Optional[Callable[[str], bool]] = None
) -> List[str]:
    """Convenience function to tick global keepalive."""
    return get_keepalive().tick(send_fn, is_busy_fn)
