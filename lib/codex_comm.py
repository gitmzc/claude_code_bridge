#!/usr/bin/env python3
"""
Codex communication module (log-driven version)
Sends requests via FIFO and parses replies from ~/.codex/sessions logs.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from base_ai_comm import BaseLogReader, BaseCommunicator
from ccb_config import apply_backend_env

apply_backend_env()

SESSION_ROOT = Path(os.environ.get("CODEX_SESSION_ROOT") or (Path.home() / ".codex" / "sessions")).expanduser()
SESSION_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


class CodexLogReader(BaseLogReader):
    """Reads Codex official logs from ~/.codex/sessions"""

    def __init__(self, root: Path = SESSION_ROOT, log_path: Optional[Path] = None, session_id_filter: Optional[str] = None):
        super().__init__(root, poll_interval=float(os.environ.get("CODEX_POLL_INTERVAL", "0.05")))
        self.set_preferred_log(log_path)
        self._session_id_filter = session_id_filter
        # Use a list to accumulate partial messages across calls if needed, 
        # but for simplicity, we'll try to rely on state passing.
        # Actually, wait_for_message in base class creates a new loop.
        # We need to handle multi-line aggregation.

    def _scan_latest(self) -> Optional[Path]:
        if not self.root.exists():
            return None
        try:
            # Avoid sorting the full list (can be slow on large histories / slow filesystems).
            latest: Optional[Path] = None
            latest_mtime = -1.0
            for p in (p for p in self.root.glob("**/*.jsonl") if p.is_file()):
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if mtime >= latest_mtime:
                    latest = p
                    latest_mtime = mtime
        except OSError:
            return None
        return latest

    def _read_and_parse(self, log_path: Path) -> Path:
        # For Codex, we don't parse the whole file upfront. We pass the path to extract.
        return log_path

    def _extract_message_from_data(self, log_path: Path, offset_info: Any = None) -> Tuple[Optional[str], Any]:
        """
        Reads from log_path starting at offset_info (int byte offset).
        Returns (message, new_offset).
        """
        byte_offset = offset_info if isinstance(offset_info, int) else 0
        partial_msgs = []
        
        # If byte_offset is None/0 initially, we might want to start at EOF for new sessions?
        # But capture_state sets the initial baseline.
        
        try:
            current_size = log_path.stat().st_size
            if byte_offset > current_size:
                byte_offset = 0
                partial_msgs = []
                
            if byte_offset == current_size:
                 return None, (byte_offset, partial_msgs)

            with log_path.open("rb") as fh:
                fh.seek(byte_offset)
                while True:
                    line = fh.readline()
                    if not line:
                        break
                    
                    # If line is incomplete (no newline), we must back off?
                    # readline() returns whatever is there. If it doesn't end in \n, 
                    # it might be incomplete write.
                    if not line.endswith(b"\n"):
                        # Keep offset here, try again later
                        break
                        
                    byte_offset = fh.tell()
                    decoded_line = line.decode("utf-8", errors="ignore").strip()
                    if not decoded_line:
                        continue
                    
                    try:
                        entry = json.loads(decoded_line)
                    except json.JSONDecodeError:
                        continue
                    
                    msg = self._extract_message_content(entry)
                    if msg is not None:
                        if "[CCB_REPLY_END]" in msg:
                            msg = msg.replace("[CCB_REPLY_END]", "").rstrip()
                            partial_msgs.append(msg)
                            merged = "\n\n".join(m for m in partial_msgs if m)
                            # Reset partials after return
                            return merged, (byte_offset, [])
                        else:
                            partial_msgs.append(msg)
                            
        except OSError:
            pass
            
        return None, (byte_offset, partial_msgs)

    def capture_state(self) -> Dict[str, Any]:
        """Capture current log path and offset"""
        log = self.current_log_path()
        offset = 0
        if log and log.exists():
            try:
                offset = log.stat().st_size
            except OSError:
                offset = 0
        return {"log_path": log, "offset_info": (offset, [])}

    def wait_for_message(self, state: Dict[str, Any], timeout: float) -> Tuple[Optional[str], Dict[str, Any]]:
        """Block and wait for new Codex reply"""
        deadline = time.time() + timeout
        log_path = state.get("log_path") or self.current_log_path()
        offset_info = state.get("offset_info", (0, []))

        while True:
            if log_path and log_path.exists():
                message, new_offset_info = self._extract_message_from_data(log_path, offset_info[0] if isinstance(offset_info, tuple) else offset_info)
                if message:
                    return message, {"log_path": log_path, "offset_info": new_offset_info}
                offset_info = new_offset_info

            if time.time() >= deadline:
                return None, {"log_path": log_path, "offset_info": offset_info}

            # Wait for file change
            if log_path and log_path.exists():
                self._watcher.wait_for_change(log_path, timeout=self._poll_interval)
            else:
                time.sleep(self._poll_interval)
                log_path = self.current_log_path()

    def try_get_message(self, state: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """Non-blocking read for reply"""
        log_path = state.get("log_path") or self.current_log_path()
        offset_info = state.get("offset_info", (0, []))

        if log_path and log_path.exists():
            message, new_offset_info = self._extract_message_from_data(log_path, offset_info[0] if isinstance(offset_info, tuple) else offset_info)
            return message, {"log_path": log_path, "offset_info": new_offset_info}

        return None, {"log_path": log_path, "offset_info": offset_info}

    def latest_message(self) -> Optional[str]:
        log_path = self.current_log_path()
        if not log_path or not log_path.exists():
            return None
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                buffer = bytearray()
                position = handle.tell()
                # Read last 256KB
                while position > 0 and len(buffer) < 1024 * 256:
                    read_size = min(4096, position)
                    position -= read_size
                    handle.seek(position)
                    buffer = handle.read(read_size) + buffer
                    if buffer.count(b"\n") >= 50:
                        break
                lines = buffer.decode("utf-8", errors="ignore").splitlines()
        except OSError:
            return None

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = self._extract_message_content(entry)
            if message:
                return message.replace("[CCB_REPLY_END]", "").strip()
        return None

    def latest_conversations(self, n: int = 1) -> List[Dict[str, str]]:
        """Get the latest N Q&A pairs from the log.

        Returns a list of dicts with 'question' and 'answer' keys.
        """
        log_path = self.current_log_path()
        if not log_path or not log_path.exists():
            return []

        try:
            with log_path.open("rb") as handle:
                content = handle.read().decode("utf-8", errors="ignore")
            lines = content.splitlines()
        except OSError:
            return []

        # Parse all entries
        conversations = []
        current_question = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Check for user input
            if entry.get("type") == "input":
                payload = entry.get("payload", {})
                if isinstance(payload, dict):
                    content = payload.get("content", "")
                    if content:
                        current_question = content.strip()

            # Check for assistant response
            message = self._extract_message_content(entry)
            if message and current_question:
                clean_message = message.replace("[CCB_REPLY_END]", "").strip()
                if clean_message:
                    conversations.append({
                        "question": current_question,
                        "answer": clean_message
                    })
                    current_question = None

        return conversations[-n:] if n > 0 else conversations

    @staticmethod
    def _extract_message_content(entry: dict) -> Optional[str]:
        if entry.get("type") != "response_item":
            return None
        payload = entry.get("payload", {})
        if payload.get("type") != "message":
            return None

        content = payload.get("content") or []
        texts = [item.get("text", "") for item in content if item.get("type") == "output_text"]
        if texts:
            return "\n".join(filter(None, texts)).strip()

        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return None


class CodexCommunicator(BaseCommunicator):
    """Communicates with Codex bridge via FIFO and reads replies from logs"""
    
    @property
    def provider_name(self) -> str:
        return "Codex"

    def _create_log_reader(self) -> CodexLogReader:
        preferred_log = self.session_info.get("codex_session_path")
        bound_session_id = self.session_info.get("codex_session_id")
        return CodexLogReader(log_path=preferred_log, session_id_filter=bound_session_id)

    def _load_session_info(self) -> Optional[Dict[str, Any]]:
        if "CODEX_SESSION_ID" in os.environ:
            terminal = os.environ.get("CODEX_TERMINAL", "tmux")
            pane_id = ""
            if terminal == "wezterm":
                pane_id = os.environ.get("CODEX_WEZTERM_PANE", "")
            elif terminal == "iterm2":
                pane_id = os.environ.get("CODEX_ITERM2_PANE", "")
            
            return {
                "session_id": os.environ["CODEX_SESSION_ID"],
                "runtime_dir": os.environ["CODEX_RUNTIME_DIR"],
                "input_fifo": os.environ["CODEX_INPUT_FIFO"],
                "output_fifo": os.environ.get("CODEX_OUTPUT_FIFO", ""),
                "terminal": terminal,
                "tmux_session": os.environ.get("CODEX_TMUX_SESSION", ""),
                "pane_id": pane_id,
                "_session_file": None,
            }

        project_session = Path.cwd() / ".codex-session"
        if not project_session.exists():
            return None

        try:
            with open(project_session, "r", encoding="utf-8-sig") as f:
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

    def _raise_no_session_error(self):
        raise RuntimeError("❌ No active Codex session found. Run 'ccb up codex' first")

    def _check_session_health_impl(self, probe_terminal: bool) -> Tuple[bool, str]:
        try:
            if not self.runtime_dir.exists():
                return False, "Runtime directory does not exist"

            # WezTerm/iTerm2 mode
            if self.terminal in ("wezterm", "iterm2"):
                if not self.pane_id:
                    return False, f"{self.terminal} pane_id not found"
                if probe_terminal and (not self.backend or not self.backend.is_alive(self.pane_id)):
                    return False, f"{self.terminal} pane does not exist: {self.pane_id}"
                return True, "Session healthy"

            # tmux mode
            codex_pid_file = self.runtime_dir / "codex.pid"
            if not codex_pid_file.exists():
                return False, "Codex process PID file not found"
            
            # Simple pid check
            try:
                with open(codex_pid_file, "r") as f:
                    os.kill(int(f.read().strip()), 0)
            except (ValueError, OSError):
                return False, "Codex process has exited"

            input_fifo = Path(self.session_info["input_fifo"])
            if not input_fifo.exists():
                return False, "Communication pipe does not exist"

            return True, "Session healthy"
        except Exception as exc:
            return False, f"Health check failed: {exc}"

    def _send_payload(self, content: str) -> Tuple[str, Dict[str, Any]]:
        marker = f"ask-{int(time.time())}-{os.getpid()}"
        message = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "marker": marker,
        }

        # Capture state BEFORE sending to ensure we don't miss immediate replies
        state = self.log_reader.capture_state()

        if self.terminal in ("wezterm", "iterm2"):
            if not self.backend or not self.pane_id:
                raise RuntimeError("Terminal session not configured")
            self.backend.send_text(self.pane_id, content)
        else:
            fifo_path = Path(self.session_info["input_fifo"])
            with open(fifo_path, "w", encoding="utf-8") as fifo:
                fifo.write(json.dumps(message, ensure_ascii=False) + "\n")
                fifo.flush()

        return marker, state

    def _prime_log_binding(self):
        log_hint = self.log_reader.current_log_path()
        if log_hint:
            self._remember_session(log_hint)

    def _remember_session(self, log_path: Path):
        try:
            log_path_obj = log_path if isinstance(log_path, Path) else Path(str(log_path)).expanduser()
        except Exception:
            return

        self.log_reader.set_preferred_log(log_path_obj)

        if not self.project_session_file:
            return

        project_file = Path(self.project_session_file)
        if not project_file.exists():
            return
        
        try:
            with project_file.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except Exception:
            return

        updated = False
        path_str = str(log_path_obj)
        if data.get("codex_session_path") != path_str:
            data["codex_session_path"] = path_str
            updated = True
        
        # Extract ID
        session_id = self._extract_session_id(log_path_obj)
        if session_id and data.get("codex_session_id") != session_id:
            data["codex_session_id"] = session_id
            updated = True

        if updated:
            self._write_session_file(project_file, data)
            self.session_info["codex_session_path"] = path_str
            if session_id:
                self.session_info["codex_session_id"] = session_id

    def _write_session_file(self, path: Path, data: dict):
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            print(f"⚠️  Failed to update {path.name}: {e}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    @staticmethod
    def _extract_session_id(log_path: Path) -> Optional[str]:
        # Reuse existing logic for ID extraction
        for source in (log_path.stem, log_path.name):
            match = SESSION_ID_PATTERN.search(source)
            if match:
                return match.group(0)
        try:
            with log_path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
                if first_line:
                    match = SESSION_ID_PATTERN.search(first_line)
                    if match: return match.group(0)
                    entry = json.loads(first_line)
                    # Check various fields...
                    # Simplified for brevity as per original code
                    pass
        except Exception:
            pass
        return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Codex communication tool (log-driven)")
    parser.add_argument("question", nargs="*", help="Question to send")
    parser.add_argument("--wait", "-w", action="store_true", help="Wait for reply synchronously")
    parser.add_argument("--timeout", type=int, default=30, help="Sync timeout in seconds")
    parser.add_argument("--ping", action="store_true", help="Test connectivity")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--pending", action="store_true", help="Show pending reply")
    args = parser.parse_args()

    try:
        comm = CodexCommunicator()

        if args.ping:
            comm.ping()
        elif args.status:
            status = comm.get_status()
            print("📊 Codex status:")
            for k, v in status.items():
                print(f"   {k}: {v}")
        elif args.pending:
            comm.consume_pending()
        elif args.question:
            tokens = list(args.question)
            if tokens and tokens[0].lower() == "ask": tokens = tokens[1:]
            q = " ".join(tokens).strip()
            if not q:
                print("❌ Please provide a question")
                return 1
            if args.wait:
                if comm.ask_sync(q, args.timeout) is None: return 1
            else:
                comm.ask_async(q)
        else:
            print("Please provide a question or use --ping/--status/--pending")
            return 1
        return 0
    except Exception as exc:
        print(f"❌ Execution failed: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())