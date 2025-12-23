import os
import shutil
import subprocess
import sys


def _is_macos() -> bool:
    return sys.platform == "darwin"


def send_notification(title: str, message: str) -> None:
    """Send a desktop notification (macOS only for now)."""
    if os.environ.get("CCB_NOTIFY", "1") not in ("1", "true", "yes"):
        return

    if _is_macos() and shutil.which("osascript"):
        # Escape quotes for AppleScript
        safe_title = title.replace('"', '\"')
        safe_message = message.replace('"', '\"')
        # Truncate message if too long
        if len(safe_message) > 100:
            safe_message = safe_message[:97] + "..."
        
        try:
            subprocess.run(
                ["osascript", "-e", f'display notification "{safe_message}" with title "{safe_title}"'],
                capture_output=True,
                check=False
            )
        except Exception:
            pass  # Fail silently for notifications


def set_terminal_title(title: str) -> None:
    """Set the terminal window title."""
    if os.environ.get("CCB_TITLE_UPDATE", "1") not in ("1", "true", "yes"):
        return

    # ANSI escape sequence for setting window title
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def notify_reply_received(provider: str, message: str) -> None:
    """Helper to send notification and update title when AI replies."""
    send_notification(f"{provider} Replied", message)
    set_terminal_title(f"✅ {provider}: Reply Received")


def notify_waiting(provider: str) -> None:
    """Helper to update title when waiting."""
    set_terminal_title(f"⏳ Waiting for {provider}...")
