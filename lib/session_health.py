"""
Session Health Detection - Prevent zombie processes, duplicate launches, and stale sessions.

Inspired by CCCC project's health detection mechanism.
Uses lock files, heartbeat timestamps, and process checks for stability.
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

# Use fcntl on Unix, msvcrt on Windows
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False


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


class SessionHealth:
    """Session health detection and lock management.

    Features:
    - Lock file to prevent duplicate launches
    - Heartbeat timestamp to detect stale sessions
    - Process alive check to detect zombie locks

    Usage:
        health = SessionHealth(Path(".codex-session"))

        # Check if another instance is running
        is_locked, pid = health.is_locked()
        if is_locked:
            print(f"Another instance (PID {pid}) is running")
            return

        # Acquire lock before starting
        if not health.acquire_lock():
            print("Failed to acquire lock")
            return

        try:
            # ... do work ...
            health.update_heartbeat()  # Periodically update
        finally:
            health.release_lock()
    """

    def __init__(self, session_file: Path, lock_timeout: float = 5.0):
        """
        Args:
            session_file: Path to session file (e.g., .codex-session)
            lock_timeout: Timeout for acquiring lock (seconds)
        """
        self.session_file = Path(session_file)
        self.lock_file = self.session_file.with_suffix('.lock')
        self.lock_timeout = lock_timeout
        self._lock_fd = None

    def acquire_lock(self) -> bool:
        """Acquire exclusive lock to prevent duplicate launches.

        Returns:
            True if lock acquired successfully, False otherwise.
        """
        if _env_bool("CCB_SKIP_LOCK"):
            return True

        try:
            self._lock_fd = open(self.lock_file, 'w')

            if HAS_FCNTL:
                # Unix: use fcntl
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif HAS_MSVCRT:
                # Windows: use msvcrt
                import msvcrt
                msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                # No locking available, just use file existence
                pass

            # Write PID to lock file
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
            return True

        except (IOError, OSError):
            if self._lock_fd:
                try:
                    self._lock_fd.close()
                except Exception:
                    pass
                self._lock_fd = None
            return False

    def release_lock(self) -> None:
        """Release the lock."""
        if self._lock_fd:
            try:
                if HAS_FCNTL:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                elif HAS_MSVCRT:
                    import msvcrt
                    try:
                        msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None

        # Remove lock file
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception:
            pass

    def is_locked(self) -> Tuple[bool, Optional[int]]:
        """Check if session is locked by another process.

        Returns:
            (is_locked, pid) - pid is the process ID holding the lock, or None.
        """
        if not self.lock_file.exists():
            return False, None

        # Try to acquire lock to test if it's held
        try:
            with open(self.lock_file, 'r+') as f:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                elif HAS_MSVCRT:
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                # Lock acquired and released - not locked
                return False, None
        except (IOError, OSError):
            # Lock is held by another process
            pass
        except Exception:
            return False, None

        # Read PID from lock file
        try:
            pid_str = self.lock_file.read_text().strip()
            pid = int(pid_str) if pid_str else None
            return True, pid
        except Exception:
            return True, None

    def is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is alive, False otherwise.
        """
        if pid is None:
            return False

        try:
            # os.kill with signal 0 doesn't kill, just checks existence
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def is_stale(self, max_age_seconds: float = None) -> bool:
        """Check if session file is stale (too old).

        Args:
            max_age_seconds: Maximum age in seconds. Default from CCB_SESSION_MAX_AGE
                            or 86400 (24 hours).

        Returns:
            True if session is stale or doesn't exist.
        """
        if max_age_seconds is None:
            max_age_seconds = _env_float("CCB_SESSION_MAX_AGE", 86400)

        if not self.session_file.exists():
            return True

        try:
            mtime = self.session_file.stat().st_mtime
            return time.time() - mtime > max_age_seconds
        except Exception:
            return True

    def update_heartbeat(self) -> None:
        """Update heartbeat by touching the session file."""
        if self.session_file.exists():
            try:
                self.session_file.touch()
            except Exception:
                pass

    def cleanup_stale(self) -> bool:
        """Clean up stale session and lock files.

        Returns:
            True if any files were cleaned up.
        """
        cleaned = False

        # Check if lock is held by dead process
        is_locked, pid = self.is_locked()
        if is_locked and pid:
            if not self.is_process_alive(pid):
                # Process is dead, clean up lock
                try:
                    self.lock_file.unlink()
                    cleaned = True
                except Exception:
                    pass

        # Check if session file is stale
        if self.is_stale():
            try:
                if self.session_file.exists():
                    self.session_file.unlink()
                    cleaned = True
            except Exception:
                pass

        return cleaned

    def get_status(self) -> dict:
        """Get comprehensive health status.

        Returns:
            Dictionary with health information.
        """
        is_locked, pid = self.is_locked()
        process_alive = self.is_process_alive(pid) if pid else False

        return {
            "session_exists": self.session_file.exists(),
            "lock_exists": self.lock_file.exists(),
            "is_locked": is_locked,
            "lock_pid": pid,
            "process_alive": process_alive,
            "is_stale": self.is_stale(),
            "session_file": str(self.session_file),
            "lock_file": str(self.lock_file),
        }


def check_session_health(session_file: Path) -> Tuple[bool, str]:
    """Convenience function to check session health.

    Args:
        session_file: Path to session file

    Returns:
        (is_healthy, status_message)
    """
    health = SessionHealth(session_file)
    status = health.get_status()

    if status["is_locked"]:
        pid = status["lock_pid"]
        if status["process_alive"]:
            return False, f"Another instance (PID {pid}) is running"
        else:
            # Dead process holding lock
            health.cleanup_stale()
            return True, "Cleaned up stale lock from dead process"

    if status["is_stale"]:
        health.cleanup_stale()
        return True, "Cleaned up stale session"

    return True, "Session healthy"


def with_session_lock(session_file: Path):
    """Decorator to run function with session lock.

    Usage:
        @with_session_lock(Path(".codex-session"))
        def my_function():
            # ... do work ...
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            health = SessionHealth(session_file)

            # Check for existing lock
            is_locked, pid = health.is_locked()
            if is_locked:
                if health.is_process_alive(pid):
                    raise RuntimeError(f"Another instance (PID {pid}) is running")
                else:
                    health.cleanup_stale()

            # Acquire lock
            if not health.acquire_lock():
                raise RuntimeError("Failed to acquire session lock")

            try:
                return func(*args, **kwargs)
            finally:
                health.release_lock()

        return wrapper
    return decorator
