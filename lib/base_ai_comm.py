"""
Base classes for AI communication (Codex/Gemini)
Abstracts common logic for log reading, session management, and message sending.
"""

from __future__ import annotations

import abc
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from fs_watcher import FileWatcher
from i18n import t
import notify
from terminal import get_backend_for_session, get_pane_id_from_session


class TimeoutAction:
    """Enum-like class for timeout actions"""
    WAIT = "wait"
    BACKGROUND = "background"
    CANCEL = "cancel"


class BaseLogReader(abc.ABC):
    """Abstract base class for reading AI session logs"""

    def __init__(self, root: Path, poll_interval: float = 0.05):
        self.root = Path(root).expanduser()
        self._poll_interval = min(0.5, max(0.01, poll_interval))
        self._watcher = FileWatcher()
        self._preferred_log: Optional[Path] = None

    @abc.abstractmethod
    def _scan_latest(self) -> Optional[Path]:
        """Find the latest log file based on provider-specific logic"""
        pass

    @abc.abstractmethod
    def capture_state(self) -> Dict[str, Any]:
        """Capture current state (file path, size/offset, mtime, etc.)"""
        pass

    @abc.abstractmethod
    def wait_for_message(self, state: Dict[str, Any], timeout: float) -> Tuple[Optional[str], Dict[str, Any]]:
        """Block and wait for new reply"""
        pass

    @abc.abstractmethod
    def try_get_message(self, state: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """Non-blocking read for reply"""
        pass

    @abc.abstractmethod
    def latest_message(self) -> Optional[str]:
        """Get the latest reply directly"""
        pass

    @abc.abstractmethod
    def latest_conversations(self, n: int = 1) -> List[Dict[str, str]]:
        """Get the latest N Q&A pairs from the log"""
        pass

    def current_log_path(self) -> Optional[Path]:
        """Get current log path, preferring sticky session if valid"""
        latest = self._scan_latest()
        if latest:
            if not self._preferred_log or not self._preferred_log.exists():
                self._preferred_log = latest
            elif latest != self._preferred_log:
                try:
                    preferred_mtime = self._preferred_log.stat().st_mtime if self._preferred_log.exists() else 0
                    latest_mtime = latest.stat().st_mtime
                    if latest_mtime > preferred_mtime:
                        self._preferred_log = latest
                except OSError:
                    self._preferred_log = latest
        return self._preferred_log if self._preferred_log and self._preferred_log.exists() else latest

    def set_preferred_log(self, log_path: Optional[Path]) -> None:
        """Set preferred log path"""
        if log_path:
            self._preferred_log = log_path if isinstance(log_path, Path) else Path(str(log_path))


class BaseCommunicator(abc.ABC):
    """Abstract base class for AI communication"""

    def __init__(self, lazy_init: bool = False):
        self.session_info = self._load_session_info()
        if not self.session_info:
            self._raise_no_session_error()

        self.session_id = self.session_info["session_id"]
        self.runtime_dir = Path(self.session_info["runtime_dir"])
        self.terminal = self.session_info.get("terminal", "tmux")
        self.pane_id = get_pane_id_from_session(self.session_info) or ""
        self.backend = get_backend_for_session(self.session_info)
        self.project_session_file = self.session_info.get("_session_file")
        self.marker_prefix = "ask"

        self._log_reader: Optional[BaseLogReader] = None
        self._log_reader_primed = False

        if not lazy_init:
            self._ensure_log_reader()
            self.check_health_strict()

    @property
    def log_reader(self) -> BaseLogReader:
        """Lazy-load log reader on first access"""
        self._ensure_log_reader()
        return self._log_reader

    def _ensure_log_reader(self) -> None:
        """Initialize log reader if not already done"""
        if self._log_reader is not None:
            return
        self._log_reader = self._create_log_reader()
        if not self._log_reader_primed:
            self._prime_log_binding()
            self._log_reader_primed = True

    @abc.abstractmethod
    def _load_session_info(self) -> Optional[Dict[str, Any]]:
        """Load session info from environment or file"""
        pass

    @abc.abstractmethod
    def _create_log_reader(self) -> BaseLogReader:
        """Create provider-specific log reader"""
        pass

    @abc.abstractmethod
    def _raise_no_session_error(self):
        """Raise provider-specific error when no session found"""
        pass

    @abc.abstractmethod
    def _check_session_health_impl(self, probe_terminal: bool) -> Tuple[bool, str]:
        """Check session health"""
        pass

    @abc.abstractmethod
    def _send_payload(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """Send content and return (marker, state_before_send)"""
        pass

    @abc.abstractmethod
    def _prime_log_binding(self):
        """Bind session to specific log file if needed"""
        pass

    @abc.abstractmethod
    def _remember_session(self, log_path: Optional[Path]):
        """Remember session path for future use"""
        pass

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return provider name (e.g., 'Codex', 'Gemini')"""
        pass

    @property
    def default_timeout(self) -> int:
        """Default timeout in seconds"""
        return 30

    def _generate_marker(self) -> str:
        """Generate unique marker for message tracking"""
        return f"{self.marker_prefix}-{int(time.time())}-{os.getpid()}"

    def check_health_strict(self):
        """Check health and raise error if unhealthy"""
        healthy, msg = self._check_session_health_impl(probe_terminal=True)
        if not healthy:
            raise RuntimeError(f"❌ Session unhealthy: {msg}")

    def get_status(self) -> Dict[str, Any]:
        """Get session status"""
        healthy, status = self._check_session_health_impl(probe_terminal=True)
        return {
            "session_id": self.session_id,
            "runtime_dir": str(self.runtime_dir),
            "healthy": healthy,
            "status": status,
            "terminal": self.terminal,
            "pane_id": self.pane_id,
        }

    def ping(self, display: bool = True) -> Tuple[bool, str]:
        """Test connectivity"""
        healthy, status = self._check_session_health_impl(probe_terminal=True)
        msg = f"✅ {self.provider_name} connection OK ({status})" if healthy else f"❌ {self.provider_name} connection error: {status}"
        if display:
            print(msg)
        return healthy, msg

    def ask_async(self, question: str) -> bool:
        """Send question without waiting for reply"""
        try:
            healthy, status = self._check_session_health_impl(probe_terminal=False)
            if not healthy:
                raise RuntimeError(f"❌ Session error: {status}")

            marker, state = self._send_payload(question)
            log_hint = state.get("log_path") or state.get("session_path") or self.log_reader.current_log_path()
            if log_hint:
                self._remember_session(log_hint)

            print(f"✅ Sent to {self.provider_name}")
            print(f"Tip: Use {self.provider_name.lower()[0]}pend to view latest reply")
            return True
        except Exception as exc:
            print(f"❌ Send failed: {exc}")
            return False

    def ask_sync(self, question: str, timeout: Optional[int] = None) -> Optional[str]:
        """Send question and wait for reply with interactive timeout handling"""
        try:
            healthy, status = self._check_session_health_impl(probe_terminal=False)
            if not healthy:
                raise RuntimeError(f"❌ Session error: {status}")

            print(f"🔔 {t('sending_to', provider=self.provider_name)}", flush=True)
            marker, state = self._send_payload(question)
            notify.notify_waiting(self.provider_name)

            # Determine timeout
            env_key = f"{self.provider_name.upper()}_SYNC_TIMEOUT"
            if timeout is None:
                wait_timeout = int(os.environ.get(env_key, self.default_timeout))
            else:
                wait_timeout = int(timeout)

            # Unlimited wait mode (timeout=0)
            if wait_timeout == 0:
                return self._wait_unlimited(state)

            # Normal wait with timeout handling
            return self._wait_with_timeout(state, wait_timeout)

        except Exception as exc:
            print(f"❌ Sync ask failed: {exc}")
            return None

    def _wait_unlimited(self, state: Dict[str, Any]) -> Optional[str]:
        """Wait indefinitely for reply"""
        print(f"⏳ {t('waiting_for_reply', provider=self.provider_name)}", flush=True)
        start_time = time.time()
        last_hint = 0
        while True:
            message, new_state = self.log_reader.wait_for_message(state, timeout=30.0)
            state = new_state or state
            self._update_session_memory(state)

            if message:
                self._handle_reply(message)
                return message

            elapsed = int(time.time() - start_time)
            if elapsed >= last_hint + 30:
                last_hint = elapsed
                print(f"⏳ Still waiting... ({elapsed}s)")

    def _wait_with_timeout(self, state: Dict[str, Any], wait_timeout: int) -> Optional[str]:
        """Wait for reply with interactive timeout handling"""
        print(f"⏳ Waiting for {self.provider_name} reply (timeout {wait_timeout}s)...")

        while True:
            message, new_state = self.log_reader.wait_for_message(state, float(wait_timeout))
            state = new_state or state
            self._update_session_memory(state)

            if message:
                self._handle_reply(message)
                return message

            # Timeout reached - ask user what to do
            action = self._handle_timeout_interactive(wait_timeout)

            if action == TimeoutAction.WAIT:
                # Continue waiting with same timeout
                print(f"⏳ Continuing to wait (timeout {wait_timeout}s)...")
                continue
            elif action == TimeoutAction.BACKGROUND:
                # Exit but keep task running
                print(f"📋 Task moved to background. Use {self.provider_name.lower()[0]}pend to check reply later.")
                return None
            else:  # CANCEL
                print(f"⏰ {t('timeout_no_reply', provider=self.provider_name)}")
                return None

    def _handle_timeout_interactive(self, wait_timeout: int) -> str:
        """Handle timeout with interactive menu (if TTY available)"""
        # Check if we're in an interactive terminal
        if not sys.stdin.isatty():
            # Non-interactive mode: check config for default action
            default_action = os.environ.get("CCB_TIMEOUT_ACTION", "cancel").lower()
            if default_action == "wait":
                return TimeoutAction.WAIT
            elif default_action == "background":
                return TimeoutAction.BACKGROUND
            return TimeoutAction.CANCEL

        print(f"\n⏳ Request timed out. {self.provider_name} hasn't replied yet.")
        print("What would you like to do?")
        print(f"  [w] Wait - Continue waiting ({wait_timeout}s more)")
        print(f"  [b] Background - Exit and check later with {self.provider_name.lower()[0]}pend")
        print("  [c] Cancel - Give up (default)")
        print()

        # Read user input with timeout
        try:
            # Try to use select for timeout on input (Unix only)
            # On Windows, select doesn't work with stdin, so we fall back to input()
            if sys.platform != "win32":
                import select
                print("Your choice (w/b/c) [c]: ", end="", flush=True)
                rlist, _, _ = select.select([sys.stdin], [], [], 10.0)
                if rlist:
                    choice = sys.stdin.readline().strip().lower()
                else:
                    print()  # Newline after timeout
                    choice = "c"
            else:
                # Windows fallback - just use input with no timeout
                choice = input("Your choice (w/b/c) [c]: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError, ValueError):
            print()
            choice = "c"

        if choice == "w":
            return TimeoutAction.WAIT
        elif choice == "b":
            return TimeoutAction.BACKGROUND
        else:
            return TimeoutAction.CANCEL

    def _update_session_memory(self, state: Optional[Dict[str, Any]]):
        """Update session memory with current state"""
        if not state:
            return
        log_path = state.get("log_path") or state.get("session_path")
        if not log_path:
            log_path = self.log_reader.current_log_path()
        if log_path:
            self._remember_session(log_path)

    def _handle_reply(self, message: str):
        """Handle received reply"""
        notify.notify_reply_received(self.provider_name, message)
        print(f"🤖 {t('reply_from', provider=self.provider_name)}")
        print(message)

    def consume_pending(self, display: bool = True) -> Optional[str]:
        """Get and display the latest pending reply"""
        current = self.log_reader.current_log_path()
        if current:
            self._remember_session(current)

        message = self.log_reader.latest_message()
        if message:
            self._remember_session(self.log_reader.current_log_path())

        if not message:
            if display:
                print(t('no_reply_available', provider=self.provider_name))
            return None

        if display:
            print(message)
        return message

    def get_conversations(self, n: int = 1, display: bool = True) -> List[Dict[str, str]]:
        """Get the latest N conversations"""
        conversations = self.log_reader.latest_conversations(n)
        if display:
            if not conversations:
                print(t('no_reply_available', provider=self.provider_name))
            else:
                for i, conv in enumerate(conversations):
                    if i > 0:
                        print("\n" + "=" * 40 + "\n")
                    print(f"Q: {conv['question']}")
                    print(f"A: {conv['answer']}")
        return conversations
