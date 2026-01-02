"""
Launcher utilities for ccb.
"""

from __future__ import annotations

import atexit
import getpass
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from constants import VERSION
from i18n import t
from path_utils import extract_session_work_dir_norm, normalize_path_for_match, work_dir_match_keys
from session_utils import check_session_writable, safe_write_session
from terminal import Iterm2Backend, WeztermBackend, detect_terminal, get_shell_type


def _get_git_info(script_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(script_dir), "log", "-1", "--format=%h %ci"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _build_keep_open_cmd(provider: str, start_cmd: str) -> str:
    if get_shell_type() == "powershell":
        return (
            f"{start_cmd}; "
            f"$code = $LASTEXITCODE; "
            f'Write-Host "`n[{provider}] exited with code $code. Press Enter to close..."; '
            f"Read-Host; "
            f"exit $code"
        )
    return (
        f"{start_cmd}; "
        f"code=$?; "
        f'echo; echo "[{provider}] exited with code $code. Press Enter to close..."; '
        f"read -r _; "
        f"exit $code"
    )


class AILauncher:
    def __init__(self, providers: list, resume: bool = False, auto: bool = False, no_claude: bool = False):
        self.providers = providers or ["codex"]
        self.resume = resume
        self.auto = auto
        self.no_claude = no_claude
        self.script_dir = Path(__file__).resolve().parent
        self.session_id = f"ai-{int(time.time())}-{os.getpid()}"
        self.temp_base = Path(tempfile.gettempdir())
        self.runtime_dir = self.temp_base / f"claude-ai-{getpass.getuser()}" / self.session_id
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._cleaned = False
        self.terminal_type = self._detect_terminal_type()
        self.wezterm_panes = {}
        self.iterm2_panes = {}
        self.processes = {}

    def _detect_terminal_type(self):
        # Forced by environment variable
        forced = (os.environ.get("CCB_TERMINAL") or os.environ.get("CODEX_TERMINAL") or "").strip().lower()
        if forced in {"wezterm", "iterm2"}:
            return forced

        # When inside WezTerm pane, force wezterm
        if os.environ.get("WEZTERM_PANE"):
            return "wezterm"
        # Only use iTerm2 split when in iTerm2 environment
        if os.environ.get("ITERM_SESSION_ID"):
            return "iterm2"

        # Use detect_terminal() for auto-detection (WezTerm preferred)
        detected = detect_terminal()
        if detected:
            return detected

        # Fallback: if nothing found, return None for later handling
        return None

    def _start_provider(self, provider: str) -> bool:
        # Handle case when no terminal detected
        if self.terminal_type is None:
            print(f"❌ {t('no_terminal_backend')}")
            print(f"   {t('solutions')}")
            print(f"   - {t('install_wezterm')}")
            print(f"   - {t('or_set_ccb_terminal')}")
            return False

        # WezTerm mode
        if self.terminal_type == "wezterm":
            print(f"🚀 {t('starting_backend', provider=provider.capitalize(), terminal='wezterm')}")
            return self._start_provider_wezterm(provider)
        elif self.terminal_type == "iterm2":
            print(f"🚀 {t('starting_backend', provider=provider.capitalize(), terminal='iterm2')}")
            return self._start_provider_iterm2(provider)
        else:
            print(f"❌ {t('unknown_provider', provider=provider)}")
            return False

    def _start_provider_wezterm(self, provider: str) -> bool:
        runtime = self.runtime_dir / provider
        runtime.mkdir(parents=True, exist_ok=True)

        start_cmd = self._get_start_cmd(provider)
        keep_open = os.environ.get("CODEX_WEZTERM_KEEP_OPEN", "1").lower() not in {"0", "false", "no", "off"}
        if keep_open:
            start_cmd = _build_keep_open_cmd(provider, start_cmd)

        backend = WeztermBackend()

        # Check for new tab mode: first provider opens new tab, subsequent split in that tab
        new_tab_mode = os.environ.get("CCB_NEW_TAB", "").lower() in {"1", "true", "yes", "on"}

        if new_tab_mode and not self.wezterm_panes:
            # First provider: spawn new tab
            pane_id = backend.spawn_new_tab(start_cmd, str(Path.cwd()))
        else:
            # Determine split direction based on pane dimensions or default layout
            if not self.wezterm_panes:
                # First provider: check pane dimensions to decide direction
                direction = self._get_smart_split_direction(backend)
            else:
                # Subsequent providers: split the first pane vertically (bottom)
                direction = "bottom"

            parent_pane = None
            if self.wezterm_panes:
                try:
                    parent_pane = next(iter(self.wezterm_panes.values()))
                except StopIteration:
                    parent_pane = None

            pane_id = backend.create_pane(start_cmd, str(Path.cwd()), direction=direction, percent=50, parent_pane=parent_pane)

        self.wezterm_panes[provider] = pane_id

        if provider == "codex":
            self._write_codex_session(runtime, pane_id=pane_id)
        else:
            self._write_gemini_session(runtime, pane_id=pane_id)

        print(f"✅ {t('started_backend', provider=provider.capitalize(), terminal='wezterm pane', pane_id=pane_id)}")
        return True

    def _get_smart_split_direction(self, backend: WeztermBackend) -> str:
        """Determine split direction based on current pane dimensions.

        - Wide pane (landscape): split right (left/right layout)
        - Tall pane (portrait): split bottom (top/bottom layout)
        """
        try:
            # Get current pane info
            result = subprocess.run(
                ["wezterm", "cli", "list", "--format", "json"],
                capture_output=True, text=True, check=True
            )
            panes = json.loads(result.stdout)

            # Find the active pane
            active_pane = None
            for pane in panes:
                if pane.get("is_active"):
                    active_pane = pane
                    break

            if active_pane:
                width = active_pane.get("size", {}).get("cols", 80)
                height = active_pane.get("size", {}).get("rows", 24)

                # If width > height * 2, it's wide enough for left/right split
                # Otherwise use top/bottom split
                if width > height * 2:
                    return "right"
                else:
                    return "bottom"
        except Exception:
            pass

        # Default to right (horizontal split)
        return "right"

    def _start_provider_iterm2(self, provider: str) -> bool:
        runtime = self.runtime_dir / provider
        runtime.mkdir(parents=True, exist_ok=True)

        start_cmd = self._get_start_cmd(provider)
        # In iTerm2 split, process exit will close pane; keep pane open by default to view exit info
        keep_open = os.environ.get("CODEX_ITERM2_KEEP_OPEN", "1").lower() not in {"0", "false", "no", "off"}
        if keep_open:
            start_cmd = (
                f"{start_cmd}; "
                f"code=$?; "
                f'echo; echo "[{provider}] exited with code $code. Press Enter to close..."; '
                f"read -r _; "
                f"exit $code"
            )
        # Layout: first backend splits to the right of current pane, subsequent backends stack below
        direction = "right" if not self.iterm2_panes else "bottom"
        parent_pane = None
        if direction == "bottom":
            try:
                parent_pane = next(iter(self.iterm2_panes.values()))
            except StopIteration:
                parent_pane = None

        backend = Iterm2Backend()
        pane_id = backend.create_pane(start_cmd, str(Path.cwd()), direction=direction, percent=50, parent_pane=parent_pane)
        self.iterm2_panes[provider] = pane_id

        if provider == "codex":
            self._write_codex_session(runtime, pane_id=pane_id)
        else:
            self._write_gemini_session(runtime, pane_id=pane_id)

        print(f"✅ {t('started_backend', provider=provider.capitalize(), terminal='iterm2 session', pane_id=pane_id)}")
        return True

    def _work_dir_strings(self, work_dir: Path) -> list[str]:
        candidates: list[str] = []
        env_pwd = os.environ.get("PWD")
        if env_pwd:
            candidates.append(env_pwd)
        candidates.append(str(work_dir))
        try:
            candidates.append(str(work_dir.resolve()))
        except Exception:
            pass
        # de-dup while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
        return result

    def _read_json_file(self, path: Path) -> dict:
        try:
            if not path.exists():
                return {}
            # Session files are written as UTF-8; on Windows PowerShell 5.1 the default encoding
            # may not be UTF-8, so always decode explicitly and tolerate UTF-8 BOM.
            raw = path.read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_json_file(self, path: Path, data: dict) -> None:
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _claude_session_file(self) -> Path:
        return Path.cwd() / ".claude-session"

    def _read_local_claude_session_id(self) -> str | None:
        data = self._read_json_file(self._claude_session_file())
        sid = data.get("claude_session_id") or data.get("session_id")
        if isinstance(sid, str) and sid.strip():
            # Guard against path-format mismatch (Windows case/slash differences, MSYS paths, etc.).
            recorded_norm = extract_session_work_dir_norm(data)
            if not recorded_norm:
                # Old/foreign session file without a recorded work dir: refuse to resume to avoid cross-project reuse.
                return None
            current_keys = work_dir_match_keys(Path.cwd())
            if current_keys and recorded_norm not in current_keys:
                return None
            return sid.strip()
        return None

    def _write_local_claude_session(self, session_id: str, active: bool = True) -> None:
        path = self._claude_session_file()
        data = self._read_json_file(path)
        work_dir = Path.cwd()
        data.update(
            {
                "claude_session_id": session_id,
                "work_dir": str(work_dir),
                "work_dir_norm": normalize_path_for_match(str(work_dir)),
                "active": bool(active),
                "started_at": data.get("started_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self._write_json_file(path, data)

    def _get_latest_codex_session_id(self) -> tuple[str | None, bool]:
        """
        Returns (session_id, has_any_history_for_cwd).
        Session id is Codex CLI's UUID used by `codex resume <id>`.
        Always scans for the latest session to avoid resuming stale sessions.
        """
        work_keys = work_dir_match_keys(Path.cwd())
        if not work_keys:
            return None, False

        # Always scan Codex session logs for the latest session bound to this cwd.
        # This ensures we always resume the most recent session, not a stale cached one.
        root = Path(os.environ.get("CODEX_SESSION_ROOT") or (Path.home() / ".codex" / "sessions")).expanduser()
        if not root.exists():
            return None, False
        try:
            logs = sorted(
                (p for p in root.glob("**/*.jsonl") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            logs = []
        for log_path in logs[:400]:
            try:
                with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                    first = handle.readline().strip()
            except OSError:
                continue
            if not first:
                continue
            try:
                entry = json.loads(first)
            except Exception:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "session_meta":
                continue
            payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
            cwd = payload.get("cwd")
            if not isinstance(cwd, str) or not cwd.strip():
                continue
            if normalize_path_for_match(cwd) not in work_keys:
                continue
            sid = payload.get("id")
            if isinstance(sid, str) and sid:
                return sid, True
        return None, False

    def _build_codex_start_cmd(self) -> str:
        cmd = "codex -c disable_paste_burst=true --full-auto" if self.auto else "codex -c disable_paste_burst=true"
        codex_resumed = False
        if self.resume:
            session_id, has_history = self._get_latest_codex_session_id()
            if session_id:
                cmd = f"{cmd} resume {session_id}"
                print(f"🔁 {t('resuming_session', provider='Codex', session_id=session_id[:8])}")
                codex_resumed = True

            if not codex_resumed:
                print(f"ℹ️ {t('no_history_fresh', provider='Codex')}")
        return cmd

    def _get_latest_gemini_project_hash(self) -> tuple[str | None, bool]:
        """
        Returns (project_hash, has_any_history_for_cwd).
        Gemini CLI stores sessions under ~/.gemini/tmp/<sha256(cwd)>/chats/.
        """
        import hashlib

        gemini_root = Path(os.environ.get("GEMINI_ROOT") or (Path.home() / ".gemini" / "tmp")).expanduser()

        candidates: list[str] = []
        try:
            candidates.append(str(Path.cwd().absolute()))
        except Exception:
            pass
        try:
            candidates.append(str(Path.cwd().resolve()))
        except Exception:
            pass
        env_pwd = (os.environ.get("PWD") or "").strip()
        if env_pwd:
            try:
                candidates.append(os.path.abspath(os.path.expanduser(env_pwd)))
            except Exception:
                candidates.append(env_pwd)

        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            project_hash = hashlib.sha256(candidate.encode()).hexdigest()
            chats_dir = gemini_root / project_hash / "chats"
            if not chats_dir.exists():
                continue
            session_files = list(chats_dir.glob("session-*.json"))
            if session_files:
                return project_hash, True

        return None, False

    def _build_gemini_start_cmd(self) -> str:
        cmd = "gemini --yolo" if self.auto else "gemini"
        if self.resume:
            _, has_history = self._get_latest_gemini_project_hash()
            if has_history:
                cmd = f"{cmd} --resume latest"
                print(f"🔁 {t('resuming_session', provider='Gemini', session_id='')}")
            else:
                print(f"ℹ️ {t('no_history_fresh', provider='Gemini')}")
        return cmd

    def _warmup_provider(self, provider: str, timeout: float = 8.0) -> bool:
        if provider == "codex":
            ping_script = self.script_dir / "bin" / "cping"
        elif provider == "gemini":
            ping_script = self.script_dir / "bin" / "gping"
        else:
            return False

        if not ping_script.exists():
            return False

        print(f"🔧 Warmup: {ping_script.name}")
        deadline = time.time() + timeout
        last_result: subprocess.CompletedProcess[str] | None = None
        sleep_s = 0.3
        while time.time() < deadline:
            last_result = subprocess.run(
                [sys.executable, str(ping_script)],
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if last_result.returncode == 0:
                out = (last_result.stdout or "").strip()
                if out:
                    print(out)
                return True
            time.sleep(sleep_s)
            sleep_s = min(1.0, sleep_s * 1.5)

        if last_result:
            out = ((last_result.stdout or "") + "\n" + (last_result.stderr or "")).strip()
            if out:
                print(out)
        print(f"⚠️ Warmup failed: {provider}")
        return False

    def _get_start_cmd(self, provider: str) -> str:
        if provider == "codex":
            # NOTE: Codex TUI has paste-burst detection; terminal injection (wezterm send-text)
            # is often detected as "paste", causing Enter to only line-break not submit. Disable detection by default.
            return self._build_codex_start_cmd()
        elif provider == "gemini":
            return self._build_gemini_start_cmd()
        return ""

    def _write_codex_session(self, runtime, pane_id=None):
        session_file = Path.cwd() / ".codex-session"

        # Pre-check permissions
        writable, reason, fix = check_session_writable(session_file)
        if not writable:
            print(f"❌ Cannot write {session_file.name}: {reason}", file=sys.stderr)
            print(f"💡 Fix: {fix}", file=sys.stderr)
            return False

        data = {}
        if session_file.exists():
            data = self._read_json_file(session_file)

        work_dir = Path.cwd()
        data.update(
            {
                "session_id": self.session_id,
                "runtime_dir": str(runtime),
                "terminal": self.terminal_type,
                "pane_id": pane_id,
                "work_dir": str(work_dir),
                "work_dir_norm": normalize_path_for_match(str(work_dir)),
                "active": True,
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        ok, err = safe_write_session(session_file, json.dumps(data, ensure_ascii=False, indent=2))
        if not ok:
            print(err, file=sys.stderr)
            return False
        return True

    def _write_gemini_session(self, runtime, pane_id=None):
        session_file = Path.cwd() / ".gemini-session"

        # Pre-check permissions
        writable, reason, fix = check_session_writable(session_file)
        if not writable:
            print(f"❌ Cannot write {session_file.name}: {reason}", file=sys.stderr)
            print(f"💡 Fix: {fix}", file=sys.stderr)
            return False

        data = {
            "session_id": self.session_id,
            "runtime_dir": str(runtime),
            "terminal": self.terminal_type,
            "pane_id": pane_id,
            "work_dir": str(Path.cwd()),
            "active": True,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        ok, err = safe_write_session(session_file, json.dumps(data, ensure_ascii=False, indent=2))
        if not ok:
            print(err, file=sys.stderr)
            return False
        return True

    def _claude_project_dir(self, work_dir: Path) -> Path:
        projects_root = Path.home() / ".claude" / "projects"
        # Claude Code uses a filesystem-friendly key derived from the working directory.
        # To handle symlinked paths (PWD) vs physical paths (resolve()), try multiple candidates.
        candidates: list[Path] = []
        env_pwd = os.environ.get("PWD")
        if env_pwd:
            try:
                candidates.append(Path(env_pwd))
            except Exception:
                pass
        candidates.extend([work_dir])
        try:
            candidates.append(work_dir.resolve())
        except Exception:
            pass

        for candidate in candidates:
            key = re.sub(r"[^A-Za-z0-9]", "-", str(candidate))
            project_dir = projects_root / key
            if project_dir.exists():
                return project_dir

        # Fallback to a best-effort key even if the directory doesn't exist yet.
        try:
            fallback_path = work_dir.resolve()
        except Exception:
            fallback_path = work_dir
        key = re.sub(r"[^A-Za-z0-9]", "-", str(fallback_path))
        return projects_root / key

    def _get_latest_claude_session_id(self) -> tuple[str | None, bool]:
        """
        Returns (session_id, has_any_history).
        - session_id: latest UUID-like session id if found (for `claude --resume <id>`).
        - has_any_history: whether this project has any Claude sessions on disk.
        """
        project_dir = self._claude_project_dir(Path.cwd())
        if not project_dir.exists():
            return None, False

        session_files = list(project_dir.glob("*.jsonl"))
        if not session_files:
            return None, False

        session_env_root = Path.home() / ".claude" / "session-env"

        uuid_sessions: list[Path] = []
        for session_file in session_files:
            try:
                uuid.UUID(session_file.stem)
                # Ignore zero-byte placeholders and sessions Claude cannot actually resume.
                if session_file.stat().st_size <= 0:
                    continue
                if not (session_env_root / session_file.stem).exists():
                    continue
                uuid_sessions.append(session_file)
            except Exception:
                continue

        if not uuid_sessions:
            return None, True

        latest = max(uuid_sessions, key=lambda p: p.stat().st_mtime)
        return latest.stem, True

    def _find_claude_cmd(self) -> str:
        """Find Claude CLI executable"""
        if sys.platform == "win32":
            for cmd in ["claude.exe", "claude.cmd", "claude.bat", "claude"]:
                path = shutil.which(cmd)
                if path:
                    return path
            npm_paths = [
                Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
                Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "claude.cmd",
            ]
            for npm_path in npm_paths:
                if npm_path.exists():
                    return str(npm_path)
        else:
            path = shutil.which("claude")
            if path:
                return path
        raise FileNotFoundError("❌ Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code")

    def _start_claude(self) -> int:
        print(f"🚀 {t('starting_claude')}")

        env = os.environ.copy()
        if "codex" in self.providers:
            runtime = self.runtime_dir / "codex"
            env["CODEX_SESSION_ID"] = self.session_id
            env["CODEX_RUNTIME_DIR"] = str(runtime)
            env["CODEX_TERMINAL"] = self.terminal_type
            if self.terminal_type == "wezterm":
                env["CODEX_WEZTERM_PANE"] = self.wezterm_panes.get("codex", "")
            elif self.terminal_type == "iterm2":
                env["CODEX_ITERM2_PANE"] = self.iterm2_panes.get("codex", "")

        if "gemini" in self.providers:
            runtime = self.runtime_dir / "gemini"
            env["GEMINI_SESSION_ID"] = self.session_id
            env["GEMINI_RUNTIME_DIR"] = str(runtime)
            env["GEMINI_TERMINAL"] = self.terminal_type
            if self.terminal_type == "wezterm":
                env["GEMINI_WEZTERM_PANE"] = self.wezterm_panes.get("gemini", "")
            elif self.terminal_type == "iterm2":
                env["GEMINI_ITERM2_PANE"] = self.iterm2_panes.get("gemini", "")

        try:
            claude_cmd = self._find_claude_cmd()
        except FileNotFoundError as e:
            print(str(e))
            return 1

        cmd = [claude_cmd]
        if self.auto:
            cmd.append("--dangerously-skip-permissions")
        if self.resume:
            # Use --continue instead of --resume <session_id> for simpler logic
            # Check if there's any history for this project before using --continue
            _, has_history = self._get_latest_claude_session_id()
            if has_history:
                cmd.append("--continue")
                print(f"🔁 {t('resuming_claude', session_id='')}")
            else:
                print(f"ℹ️ {t('no_claude_session')}")

        print(f"📋 Session ID: {self.session_id}")
        print(f"📁 Runtime dir: {self.runtime_dir}")
        print(f"🔌 Active backends: {', '.join(self.providers)}")
        print()
        print("🎯 Available commands:")
        if "codex" in self.providers:
            print("   cask/cask-w/cping/cpend - Codex communication")
        if "gemini" in self.providers:
            print("   gask/gask-w/gping/gpend - Gemini communication")
        print()
        print(f"Executing: {' '.join(cmd)}")

        try:
            return subprocess.run(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, env=env).returncode
        except KeyboardInterrupt:
            print(f"\n⚠️ {t('user_interrupted')}")
            return 130

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        print(f"\n🧹 {t('cleaning_up')}")

        if self.terminal_type == "wezterm":
            backend = WeztermBackend()
            for provider, pane_id in self.wezterm_panes.items():
                if pane_id:
                    backend.kill_pane(pane_id)
        elif self.terminal_type == "iterm2":
            backend = Iterm2Backend()
            for provider, pane_id in self.iterm2_panes.items():
                if pane_id:
                    backend.kill_pane(pane_id)

        for session_file in [Path.cwd() / ".codex-session", Path.cwd() / ".gemini-session", Path.cwd() / ".claude-session"]:
            if session_file.exists():
                try:
                    data = self._read_json_file(session_file)
                    if not data:
                        continue
                    data["active"] = False
                    data["ended_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    safe_write_session(session_file, json.dumps(data, ensure_ascii=False, indent=2))
                except Exception:
                    pass

        if self.runtime_dir.exists():
            shutil.rmtree(self.runtime_dir, ignore_errors=True)

        print(f"✅ {t('cleanup_complete')}")

    def run_up(self) -> int:
        git_info = _get_git_info(self.script_dir)
        version_str = f"v{VERSION}" + (f" ({git_info})" if git_info else "")
        print(f"🚀 Claude Code Bridge {version_str}")
        print(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔌 Backends: {', '.join(self.providers)}")
        print("=" * 50)

        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, lambda s, f: (self.cleanup(), sys.exit(0)))
        signal.signal(signal.SIGTERM, lambda s, f: (self.cleanup(), sys.exit(0)))

        providers = list(self.providers)
        # Stable layout: codex on top, gemini on bottom (when both are present).
        order = {"codex": 0, "gemini": 1}
        providers.sort(key=lambda p: order.get(p, 99))

        for provider in providers:
            if not self._start_provider(provider):
                return 1
            self._warmup_provider(provider)

        if self.no_claude:
            print(f"✅ {t('backends_started_no_claude')}")
            print()
            for provider in self.providers:
                if self.terminal_type == "wezterm":
                    pane = self.wezterm_panes.get(provider, "")
                    if pane:
                        print(f"   {provider}: wezterm cli activate-pane --pane-id {pane}")
                elif self.terminal_type == "iterm2":
                    pane = self.iterm2_panes.get(provider, "")
                    if pane:
                        print(f"   {provider}: it2 session focus {pane}")
            print()
            print(f"Kill: ccb kill {' '.join(self.providers)}")
            atexit.unregister(self.cleanup)
            return 0

        try:
            return self._start_claude()
        finally:
            self.cleanup()
