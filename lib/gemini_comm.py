#!/usr/bin/env python3
"""
Gemini communication module
Supports WezTerm and iTerm2 terminals, reads replies from ~/.gemini/tmp/<hash>/chats/session-*.json
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from base_ai_comm import BaseLogReader, BaseCommunicator
from ccb_config import apply_backend_env


apply_backend_env()

GEMINI_ROOT = Path(os.environ.get("GEMINI_ROOT") or (Path.home() / ".gemini" / "tmp")).expanduser()


def _get_project_hash(work_dir: Optional[Path] = None) -> str:
    """Calculate project directory hash (consistent with gemini-cli's Storage.getFilePathHash)"""
    path = work_dir or Path.cwd()
    # gemini-cli uses Node.js path.resolve() (doesn't resolve symlinks),
    # so we use absolute() instead of resolve() to avoid hash mismatch on WSL/Windows.
    try:
        normalized = str(path.expanduser().absolute())
    except Exception:
        normalized = str(path)
    return hashlib.sha256(normalized.encode()).hexdigest()


class GeminiLogReader(BaseLogReader):
    """Reads Gemini session files from ~/.gemini/tmp/<hash>/chats"""

    def __init__(self, root: Path = GEMINI_ROOT, work_dir: Optional[Path] = None):
        try:
            poll = float(os.environ.get("GEMINI_POLL_INTERVAL", "0.05"))
        except Exception:
            poll = 0.05
        super().__init__(root, poll_interval=poll)
        self.work_dir = work_dir or Path.cwd()
        forced_hash = os.environ.get("GEMINI_PROJECT_HASH", "").strip()
        self._project_hash = forced_hash or _get_project_hash(self.work_dir)
        # Some filesystems only update mtime at 1s granularity. When waiting for a reply,
        # force a read periodically to avoid missing in-place updates that keep size/mtime unchanged.
        try:
            force = float(os.environ.get("GEMINI_FORCE_READ_INTERVAL", "1.0"))
        except Exception:
            force = 1.0
        self._force_read_interval = min(5.0, max(0.2, force))

    def set_preferred_log(self, log_path: Optional[Path]) -> None:
        if not log_path:
            return
        try:
            candidate = log_path if isinstance(log_path, Path) else Path(str(log_path)).expanduser()
        except Exception:
            return
        if candidate.exists():
            self._preferred_log = candidate
            try:
                project_hash = candidate.parent.parent.name
                if project_hash:
                    self._project_hash = project_hash
            except Exception:
                pass

    def _chats_dir(self) -> Optional[Path]:
        chats = self.root / self._project_hash / "chats"
        return chats if chats.exists() else None

    def _scan_latest_session_any_project(self) -> Optional[Path]:
        """Scan latest session across all projectHash (fallback for Windows/WSL path hash mismatch)"""
        if not self.root.exists():
            return None
        try:
            sessions = sorted(
                (p for p in self.root.glob("*/chats/session-*.json") if p.is_file() and not p.name.startswith(".")),
                key=lambda p: p.stat().st_mtime,
            )
        except OSError:
            return None
        return sessions[-1] if sessions else None

    def _scan_latest_session(self) -> Optional[Path]:
        chats = self._chats_dir()
        try:
            if chats:
                sessions = sorted(
                    (p for p in chats.glob("session-*.json") if p.is_file() and not p.name.startswith(".")),
                    key=lambda p: p.stat().st_mtime,
                )
            else:
                sessions = []
        except OSError:
            sessions = []

        if sessions:
            return sessions[-1]

        # fallback: projectHash may mismatch due to path normalization differences (Windows/WSL, symlinks, etc.)
        return self._scan_latest_session_any_project()

    def _scan_latest(self) -> Optional[Path]:
        return self._scan_latest_session()

    def _latest_session(self) -> Optional[Path]:
        preferred = self._preferred_log
        # Always scan for latest to detect if preferred is stale
        latest = self._scan_latest_session()
        if latest:
            # If preferred is stale (different file or older), update it
            if not preferred or not preferred.exists() or latest != preferred:
                try:
                    preferred_mtime = preferred.stat().st_mtime if preferred and preferred.exists() else 0
                    latest_mtime = latest.stat().st_mtime
                    if latest_mtime > preferred_mtime:
                        self._preferred_log = latest
                        try:
                            project_hash = latest.parent.parent.name
                            if project_hash:
                                self._project_hash = project_hash
                        except Exception:
                            pass
                        return latest
                except OSError:
                    self._preferred_log = latest
                    return latest
            return preferred
        return preferred if preferred and preferred.exists() else None

    def current_log_path(self) -> Optional[Path]:
        return self._latest_session()

    def capture_state(self) -> Dict[str, Any]:
        """Record current session file and message count"""
        session = self._latest_session()
        msg_count = 0
        mtime = 0.0
        mtime_ns = 0
        size = 0
        last_gemini_id: Optional[str] = None
        last_gemini_hash: Optional[str] = None
        if session and session.exists():
            data: Optional[dict] = None
            try:
                stat = session.stat()
                mtime = stat.st_mtime
                mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
                size = stat.st_size
            except OSError:
                stat = None

            # The session JSON may be written in-place; retry briefly to avoid transient JSONDecodeError.
            for attempt in range(10):
                try:
                    with session.open("r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
                    break
                except json.JSONDecodeError:
                    if attempt < 9:
                        time.sleep(min(self._poll_interval, 0.05))
                    continue
                except OSError:
                    break

            if data is None:
                # Unknown baseline (parse failed). Let the wait loop establish a stable baseline first.
                msg_count = -1
            else:
                msg_count = len(data.get("messages", []))
                last = self._extract_last_gemini(data)
                if last:
                    last_gemini_id, content = last
                    last_gemini_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "session_path": session,
            "msg_count": msg_count,
            "mtime": mtime,
            "mtime_ns": mtime_ns,
            "size": size,
            "last_gemini_id": last_gemini_id,
            "last_gemini_hash": last_gemini_hash,
        }

    def wait_for_message(self, state: Dict[str, Any], timeout: float) -> Tuple[Optional[str], Dict[str, Any]]:
        """Block and wait for new Gemini reply"""
        return self._read_since(state, timeout, block=True)

    def try_get_message(self, state: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """Non-blocking read reply"""
        return self._read_since(state, timeout=0.0, block=False)

    def latest_message(self) -> Optional[str]:
        """Get the latest Gemini reply directly"""
        session = self._latest_session()
        if not session or not session.exists():
            return None
        try:
            with session.open("r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            for msg in reversed(messages):
                if msg.get("type") == "gemini":
                    return msg.get("content", "").strip()
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def latest_conversations(self, n: int = 1) -> List[Dict[str, str]]:
        """Get the latest N Q&A pairs from the session.

        Returns a list of dicts with 'question' and 'answer' keys.
        """
        session = self._latest_session()
        if not session or not session.exists():
            return []

        try:
            with session.open("r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
        except (OSError, json.JSONDecodeError):
            return []

        # Extract Q&A pairs
        # Gemini session format: messages with type="user" (question) and type="gemini" (answer)
        conversations = []
        current_question = None

        for msg in messages:
            msg_type = msg.get("type")
            content = msg.get("content", "").strip()

            if msg_type == "user" and content:
                current_question = content
            elif msg_type == "gemini" and content and current_question:
                # Clean up markers
                clean_content = content.replace("[CCB_REPLY_END]", "").replace("[GEMINI_TURN_END]", "").strip()
                if clean_content:
                    conversations.append({
                        "question": current_question,
                        "answer": clean_content
                    })
                    current_question = None

        # Return the last N conversations
        return conversations[-n:] if n > 0 else conversations

    def _read_since(self, state: Dict[str, Any], timeout: float, block: bool) -> Tuple[Optional[str], Dict[str, Any]]:
        deadline = time.time() + timeout
        prev_count = state.get("msg_count", 0)
        unknown_baseline = isinstance(prev_count, int) and prev_count < 0
        prev_mtime = state.get("mtime", 0.0)
        prev_mtime_ns = state.get("mtime_ns")
        if prev_mtime_ns is None:
            prev_mtime_ns = int(float(prev_mtime) * 1_000_000_000)
        prev_size = state.get("size", 0)
        prev_session = state.get("session_path")
        prev_last_gemini_id = state.get("last_gemini_id")
        prev_last_gemini_hash = state.get("last_gemini_hash")
        # Allow short timeout to scan new session files (gask-w defaults 1s/poll)
        rescan_interval = min(2.0, max(0.2, timeout / 2.0))
        last_rescan = time.time()
        last_forced_read = time.time()

        while True:
            # Periodically rescan to detect new session files
            if time.time() - last_rescan >= rescan_interval:
                latest = self._scan_latest_session()
                if latest and latest != self._preferred_log:
                    self._preferred_log = latest
                    # New session file, reset counters
                    if latest != prev_session:
                        prev_count = 0
                        prev_mtime = 0.0
                        prev_size = 0
                        prev_last_gemini_id = None
                        prev_last_gemini_hash = None
                last_rescan = time.time()

            session = self._latest_session()
            chats_dir = self._chats_dir()
            if not session or not session.exists():
                if not block:
                    return None, {
                        "session_path": None,
                        "msg_count": 0,
                        "mtime": 0.0,
                        "size": 0,
                        "last_gemini_id": prev_last_gemini_id,
                        "last_gemini_hash": prev_last_gemini_hash,
                    }
                if chats_dir and chats_dir.exists():
                    self._watcher.wait_for_change(chats_dir, timeout=self._poll_interval)
                elif self.root.exists():
                    self._watcher.wait_for_change(self.root, timeout=self._poll_interval)
                else:
                    time.sleep(self._poll_interval)

                if time.time() >= deadline:
                    return None, state
                continue

            try:
                stat = session.stat()
                current_mtime = stat.st_mtime
                current_mtime_ns = getattr(stat, "st_mtime_ns", int(current_mtime * 1_000_000_000))
                current_size = stat.st_size
                # On Windows/WSL, mtime may have second-level precision, which can miss rapid writes.
                # Use file size as additional change signal.
                if block and current_mtime_ns <= prev_mtime_ns and current_size == prev_size:
                    if time.time() - last_forced_read < self._force_read_interval:
                        if not self._watcher.wait_for_change(session, timeout=self._poll_interval):
                            if time.time() >= deadline:
                                return None, {
                                    "session_path": session,
                                    "msg_count": prev_count,
                                    "mtime": prev_mtime,
                                    "mtime_ns": prev_mtime_ns,
                                    "size": prev_size,
                                    "last_gemini_id": prev_last_gemini_id,
                                    "last_gemini_hash": prev_last_gemini_hash,
                                }
                            continue

                with session.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                last_forced_read = time.time()
                messages = data.get("messages", [])
                current_count = len(messages)

                if unknown_baseline:
                    last_msg = messages[-1] if messages else None
                    if isinstance(last_msg, dict):
                        last_type = last_msg.get("type")
                        last_content = (last_msg.get("content") or "").strip()
                    else:
                        last_type = None
                        last_content = ""

                    if (
                        last_type == "gemini"
                        and last_content
                        and (current_mtime_ns > prev_mtime_ns or current_size != prev_size)
                    ):
                        msg_id = last_msg.get("id") if isinstance(last_msg, dict) else None
                        if "[CCB_REPLY_END]" in last_content:
                            last_content = last_content.replace("[CCB_REPLY_END]", "").replace("[GEMINI_TURN_END]", "").rstrip()

                        content_hash = hashlib.sha256(last_content.encode("utf-8")).hexdigest()
                        return last_content, {
                            "session_path": session,
                            "msg_count": current_count,
                            "mtime": current_mtime,
                            "mtime_ns": current_mtime_ns,
                            "size": current_size,
                            "last_gemini_id": msg_id,
                            "last_gemini_hash": content_hash,
                        }

                    prev_mtime = current_mtime
                    prev_mtime_ns = current_mtime_ns
                    prev_size = current_size
                    prev_count = current_count
                    last = self._extract_last_gemini(data)
                    if last:
                        prev_last_gemini_id, content = last
                        prev_last_gemini_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None
                    unknown_baseline = False
                    if not block:
                        return None, {
                            "session_path": session,
                            "msg_count": prev_count,
                            "mtime": prev_mtime,
                            "mtime_ns": prev_mtime_ns,
                            "size": prev_size,
                            "last_gemini_id": prev_last_gemini_id,
                            "last_gemini_hash": prev_last_gemini_hash,
                        }
                    self._watcher.wait_for_change(session, timeout=self._poll_interval)
                    if time.time() >= deadline:
                        return None, {
                            "session_path": session,
                            "msg_count": prev_count,
                            "mtime": prev_mtime,
                            "mtime_ns": prev_mtime_ns,
                            "size": prev_size,
                            "last_gemini_id": prev_last_gemini_id,
                            "last_gemini_hash": prev_last_gemini_hash,
                        }
                    continue

                if current_count > prev_count:
                    gemini_contents = []
                    last_gemini_id = None
                    last_gemini_hash = None
                    seen_hashes = set()
                    fast_exit_triggered = False

                    if prev_last_gemini_hash:
                        seen_hashes.add(prev_last_gemini_hash)
                    for msg in messages[prev_count:]:
                        if msg.get("type") == "gemini":
                            content = msg.get("content", "").strip()
                            if content:
                                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                                if content_hash in seen_hashes:
                                    continue
                                seen_hashes.add(content_hash)
                                gemini_contents.append(content)
                                last_gemini_id = msg.get("id")
                                last_gemini_hash = content_hash
                                if "[CCB_REPLY_END]" in content:
                                    fast_exit_triggered = True

                    if not gemini_contents:
                        prev_count = current_count
                        prev_mtime = current_mtime
                        prev_mtime_ns = current_mtime_ns
                        prev_size = current_size
                        if not block:
                            return None, {
                                "session_path": session,
                                "msg_count": prev_count,
                                "mtime": prev_mtime,
                                "mtime_ns": prev_mtime_ns,
                                "size": prev_size,
                                "last_gemini_id": prev_last_gemini_id,
                                "last_gemini_hash": prev_last_gemini_hash,
                            }
                        self._watcher.wait_for_change(session, timeout=self._poll_interval)
                        if time.time() >= deadline:
                            return None, {
                                "session_path": session,
                                "msg_count": prev_count,
                                "mtime": prev_mtime,
                                "mtime_ns": prev_mtime_ns,
                                "size": prev_size,
                                "last_gemini_id": prev_last_gemini_id,
                                "last_gemini_hash": prev_last_gemini_hash,
                            }
                        continue

                    if gemini_contents:
                        if block and not fast_exit_triggered:
                            remaining_time = max(0, deadline - time.time())
                            marker_timeout = max(remaining_time, 600.0) if timeout > 0 else 600.0
                            marker_check_interval = 2.0
                            marker_deadline = time.time() + marker_timeout

                            while time.time() < marker_deadline and not fast_exit_triggered:
                                self._watcher.wait_for_change(session, timeout=marker_check_interval)
                                try:
                                    with session.open("r", encoding="utf-8") as f2:
                                        data2 = json.load(f2)
                                    messages2 = data2.get("messages", [])
                                    if len(messages2) > current_count:
                                        current_count = len(messages2)
                                        gemini_contents = []
                                        seen_hashes = set()
                                        if prev_last_gemini_hash:
                                            seen_hashes.add(prev_last_gemini_hash)
                                        for msg in messages2[prev_count:]:
                                            if msg.get("type") == "gemini":
                                                content = msg.get("content", "").strip()
                                                if content:
                                                    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                                                    if content_hash in seen_hashes:
                                                        continue
                                                    seen_hashes.add(content_hash)
                                                    gemini_contents.append(content)
                                                    last_gemini_id = msg.get("id")
                                                    last_gemini_hash = content_hash
                                                    if "[CCB_REPLY_END]" in content:
                                                        fast_exit_triggered = True
                                        if fast_exit_triggered:
                                            break
                                        continue

                                    for msg in messages2[prev_count:]:
                                        if msg.get("type") == "gemini":
                                            content = msg.get("content", "").strip()
                                            if content and "[CCB_REPLY_END]" in content:
                                                fast_exit_triggered = True
                                                gemini_contents = []
                                                seen_hashes = set()
                                                if prev_last_gemini_hash:
                                                    seen_hashes.add(prev_last_gemini_hash)
                                                for m in messages2[prev_count:]:
                                                    if m.get("type") == "gemini":
                                                        c = m.get("content", "").strip()
                                                        if c:
                                                            c_hash = hashlib.sha256(c.encode("utf-8")).hexdigest()
                                                            if c_hash in seen_hashes:
                                                                continue
                                                            seen_hashes.add(c_hash)
                                                            gemini_contents.append(c)
                                                            last_gemini_id = m.get("id")
                                                            last_gemini_hash = c_hash
                                                break

                                    if fast_exit_triggered:
                                        break

                                    last2 = self._extract_last_gemini(data2)
                                    if last2:
                                        last2_id, last2_content = last2
                                        if last2_content:
                                            if "[CCB_REPLY_END]" in last2_content:
                                                fast_exit_triggered = True
                                                if gemini_contents and last_gemini_hash:
                                                    gemini_contents[-1] = last2_content
                                                last_gemini_id = last2_id
                                                last_gemini_hash = hashlib.sha256(last2_content.encode("utf-8")).hexdigest()
                                                break

                                            last2_hash = hashlib.sha256(last2_content.encode("utf-8")).hexdigest()
                                            if last2_hash != last_gemini_hash:
                                                if gemini_contents and last_gemini_hash:
                                                    gemini_contents[-1] = last2_content
                                                last_gemini_id = last2_id
                                                last_gemini_hash = last2_hash
                                                continue
                                    continue
                                except (OSError, json.JSONDecodeError):
                                    break

                        cleaned_contents = []
                        for c in gemini_contents:
                            if "[CCB_REPLY_END]" in c:
                                c = c.replace("[CCB_REPLY_END]", "").replace("[GEMINI_TURN_END]", "").rstrip()
                            cleaned_contents.append(c)

                        merged_content = "\n\n".join(cleaned_contents)
                        new_state = {
                            "session_path": session,
                            "msg_count": current_count,
                            "mtime": current_mtime,
                            "mtime_ns": current_mtime_ns,
                            "size": current_size,
                            "last_gemini_id": last_gemini_id,
                            "last_gemini_hash": last_gemini_hash,
                        }
                        return merged_content, new_state

                prev_mtime = current_mtime
                prev_mtime_ns = current_mtime_ns
                prev_count = current_count
                prev_size = current_size
                last = self._extract_last_gemini(data)
                if last:
                    prev_last_gemini_id, content = last
                    prev_last_gemini_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else prev_last_gemini_hash

            except (OSError, json.JSONDecodeError):
                pass

            if not block:
                return None, {
                    "session_path": session,
                    "msg_count": prev_count,
                    "mtime": prev_mtime,
                    "mtime_ns": prev_mtime_ns,
                    "size": prev_size,
                    "last_gemini_id": prev_last_gemini_id,
                    "last_gemini_hash": prev_last_gemini_hash,
                }

            self._watcher.wait_for_change(session, timeout=self._poll_interval)

            if time.time() >= deadline:
                return None, {
                    "session_path": session,
                    "msg_count": prev_count,
                    "mtime": prev_mtime,
                    "mtime_ns": prev_mtime_ns,
                    "size": prev_size,
                    "last_gemini_id": prev_last_gemini_id,
                    "last_gemini_hash": prev_last_gemini_hash,
                }

    @staticmethod
    def _extract_last_gemini(payload: dict) -> Optional[Tuple[Optional[str], str]]:
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not isinstance(messages, list):
            return None
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if msg.get("type") != "gemini":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            return msg.get("id"), content.strip()
        return None


class GeminiCommunicator(BaseCommunicator):
    """Communicate with Gemini via terminal and read replies from session files"""

    @property
    def provider_name(self) -> str:
        return "Gemini"

    @property
    def default_timeout(self) -> int:
        return int(os.environ.get("GEMINI_SYNC_TIMEOUT", "60"))

    def _load_session_info(self) -> Optional[Dict[str, Any]]:
        if "GEMINI_SESSION_ID" in os.environ:
            terminal = os.environ.get("GEMINI_TERMINAL", "wezterm")
            if terminal == "wezterm":
                pane_id = os.environ.get("GEMINI_WEZTERM_PANE", "")
            elif terminal == "iterm2":
                pane_id = os.environ.get("GEMINI_ITERM2_PANE", "")
            else:
                pane_id = ""
            return {
                "session_id": os.environ["GEMINI_SESSION_ID"],
                "runtime_dir": os.environ.get("GEMINI_RUNTIME_DIR", ""),
                "terminal": terminal,
                "pane_id": pane_id,
                "_session_file": None,
            }

        project_session = Path.cwd() / ".gemini-session"
        if not project_session.exists():
            return None

        try:
            with open(project_session, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict) or not data.get("active", False):
                return None

            runtime_dir = Path(data.get("runtime_dir", ""))
            if not runtime_dir.exists():
                return None

            data["_session_file"] = str(project_session)
            return data

        except Exception:
            return None

    def _create_log_reader(self) -> GeminiLogReader:
        work_dir_hint = self.session_info.get("work_dir")
        log_work_dir = Path(work_dir_hint) if isinstance(work_dir_hint, str) and work_dir_hint else None
        reader = GeminiLogReader(work_dir=log_work_dir)
        preferred_session = self.session_info.get("gemini_session_path") or self.session_info.get("session_path")
        if preferred_session:
            reader.set_preferred_log(Path(str(preferred_session)))
        return reader

    def _raise_no_session_error(self):
        raise RuntimeError("❌ No active Gemini session found, please run ccb up gemini first")

    def _check_session_health_impl(self, probe_terminal: bool) -> Tuple[bool, str]:
        try:
            if not self.runtime_dir.exists():
                return False, "Runtime directory not found"
            if not self.pane_id:
                return False, "Session ID not found"
            if probe_terminal and self.backend and not self.backend.is_alive(self.pane_id):
                return False, f"{self.terminal} session {self.pane_id} not found"
            return True, "Session OK"
        except Exception as exc:
            return False, f"Check failed: {exc}"

    def _send_payload(self, content: str) -> Tuple[str, Dict[str, Any]]:
        if not self.backend or not self.pane_id:
            raise RuntimeError("Terminal session not configured")
        marker = self._generate_marker()
        state = self.log_reader.capture_state()
        self.backend.send_text(self.pane_id, content)
        return marker, state

    def _prime_log_binding(self) -> None:
        session_path = self.log_reader.current_log_path()
        if session_path:
            self._remember_session(session_path)

    def _remember_session(self, log_path: Optional[Path]) -> None:
        if not log_path:
            return
        try:
            session_path = log_path if isinstance(log_path, Path) else Path(str(log_path)).expanduser()
        except Exception:
            return
        if not session_path.exists():
            return

        self.log_reader.set_preferred_log(session_path)

        if not self.project_session_file:
            return
        project_file = Path(self.project_session_file)
        if not project_file.exists():
            return

        try:
            with project_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return

        updated = False
        session_path_str = str(session_path)
        if data.get("gemini_session_path") != session_path_str:
            data["gemini_session_path"] = session_path_str
            updated = True

        try:
            project_hash = session_path.parent.parent.name
        except Exception:
            project_hash = ""
        if project_hash and data.get("gemini_project_hash") != project_hash:
            data["gemini_project_hash"] = project_hash
            updated = True

        session_id = ""
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("sessionId"), str):
                session_id = payload["sessionId"]
        except Exception:
            session_id = ""
        if session_id and data.get("gemini_session_id") != session_id:
            data["gemini_session_id"] = session_id
            updated = True

        if not updated:
            return

        tmp_file = project_file.with_suffix(".tmp")
        try:
            with tmp_file.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_file, project_file)
        except PermissionError as e:
            print(f"⚠️  Cannot update {project_file.name}: {e}", file=sys.stderr)
            print(f"💡 Try: sudo chown $USER:$USER {project_file}", file=sys.stderr)
            try:
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            print(f"⚠️  Failed to update {project_file.name}: {e}", file=sys.stderr)
            try:
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

        self.session_info["gemini_session_path"] = session_path_str
        if project_hash:
            self.session_info["gemini_project_hash"] = project_hash
        if session_id:
            self.session_info["gemini_session_id"] = session_id


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Gemini communication tool")
    parser.add_argument("question", nargs="*", help="Question to send")
    parser.add_argument("--wait", "-w", action="store_true", help="Wait for reply synchronously")
    parser.add_argument("--timeout", type=int, default=60, help="Sync timeout in seconds")
    parser.add_argument("--ping", action="store_true", help="Test connectivity")
    parser.add_argument("--status", action="store_true", help="View status")
    parser.add_argument("--pending", action="store_true", help="View pending reply")

    args = parser.parse_args()

    try:
        comm = GeminiCommunicator()

        if args.ping:
            comm.ping()
        elif args.status:
            status = comm.get_status()
            print("📊 Gemini status:")
            for key, value in status.items():
                print(f"   {key}: {value}")
        elif args.pending:
            comm.consume_pending()
        elif args.question:
            question_text = " ".join(args.question).strip()
            if not question_text:
                print("❌ Please provide a question")
                return 1
            if args.wait:
                if comm.ask_sync(question_text, args.timeout) is None:
                    return 1
            else:
                comm.ask_async(question_text)
        else:
            print("Please provide a question or use --ping/--status/--pending")
            return 1
        return 0
    except Exception as exc:
        print(f"❌ Execution failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
