#!/usr/bin/env python3
"""
ccb doctor - System diagnostic tool
Checks system configuration and dependencies
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

from i18n import t


class DiagnosticCheck:
    """Represents a single diagnostic check"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.passed = False
        self.message = ""
        self.suggestion = ""

    def pass_check(self, message: str = ""):
        self.passed = True
        self.message = message

    def fail_check(self, message: str, suggestion: str = ""):
        self.passed = False
        self.message = message
        self.suggestion = suggestion


def check_python_version() -> DiagnosticCheck:
    """Check Python version >= 3.10"""
    check = DiagnosticCheck("Python Version", "Python 3.10+ required")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major >= 3 and version.minor >= 10:
        check.pass_check(f"Python {version_str}")
    else:
        check.fail_check(
            f"Python {version_str} (requires 3.10+)",
            "Install Python 3.10 or later: https://www.python.org/downloads/"
        )

    return check


def check_terminal_backend() -> DiagnosticCheck:
    """Check for available terminal backends"""
    check = DiagnosticCheck("Terminal Backend", "At least one terminal backend required")

    backends = []

    # Check WezTerm
    if shutil.which("wezterm"):
        try:
            result = subprocess.run(
                ["wezterm", "cli", "list", "--format=json"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                backends.append("WezTerm")
        except Exception:
            pass

    # Check iTerm2 (macOS only)
    if platform.system() == "Darwin":
        if shutil.which("it2"):
            backends.append("iTerm2")
        elif Path("/Applications/iTerm.app").exists():
            backends.append("iTerm2 (it2 CLI not installed)")

    # Check tmux
    if shutil.which("tmux"):
        backends.append("tmux")

    if backends:
        check.pass_check(", ".join(backends))
    else:
        check.fail_check(
            "No terminal backend found",
            "Install one of: WezTerm (recommended), iTerm2 (macOS), or tmux"
        )

    return check


def check_codex_cli() -> DiagnosticCheck:
    """Check Codex CLI installation"""
    check = DiagnosticCheck("Codex CLI", "OpenAI Codex CLI tool")

    if shutil.which("codex"):
        try:
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                check.pass_check(version[:50] if version else "Installed")
            else:
                check.fail_check(
                    "Installed but not working",
                    "Try reinstalling: npm install -g @openai/codex"
                )
        except Exception as e:
            check.fail_check(
                f"Error checking version: {e}",
                "Try reinstalling: npm install -g @openai/codex"
            )
    else:
        check.fail_check(
            "Not installed",
            "Install Codex CLI: npm install -g @openai/codex"
        )

    return check


def check_gemini_cli() -> DiagnosticCheck:
    """Check Gemini CLI installation"""
    check = DiagnosticCheck("Gemini CLI", "Google Gemini CLI tool")

    if shutil.which("gemini"):
        try:
            result = subprocess.run(
                ["gemini", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                check.pass_check(version[:50] if version else "Installed")
            else:
                check.fail_check(
                    "Installed but not working",
                    "Try reinstalling: npm install -g @google/gemini-cli"
                )
        except Exception as e:
            check.fail_check(
                f"Error checking version: {e}",
                "Try reinstalling: npm install -g @google/gemini-cli"
            )
    else:
        check.fail_check(
            "Not installed",
            "Install Gemini CLI: npm install -g @google/gemini-cli"
        )

    return check


def check_session_files() -> DiagnosticCheck:
    """Check session file status in current directory"""
    check = DiagnosticCheck("Session Files", "Session configuration in current directory")

    cwd = Path.cwd()
    codex_session = cwd / ".codex-session"
    gemini_session = cwd / ".gemini-session"

    sessions = []
    if codex_session.exists():
        sessions.append("Codex")
    if gemini_session.exists():
        sessions.append("Gemini")

    if sessions:
        check.pass_check(f"Found: {', '.join(sessions)}")
    else:
        check.pass_check("No active sessions (this is normal)")

    return check


def check_config_file() -> DiagnosticCheck:
    """Check ccb configuration file"""
    check = DiagnosticCheck("Configuration", "ccb configuration file")

    config_locations = [
        Path.cwd() / ".ccb-config.json",
        Path.home() / ".config" / "ccb" / "config.json",
        Path.home() / ".ccb-config.json",
    ]

    for config_path in config_locations:
        if config_path.exists():
            check.pass_check(f"Found: {config_path}")
            return check

    check.pass_check("No config file (using defaults)")
    return check


def check_claude_integration() -> DiagnosticCheck:
    """Check Claude Code integration"""
    check = DiagnosticCheck("Claude Integration", "Claude Code configuration")

    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    settings_json = Path.home() / ".claude" / "settings.json"

    issues = []
    found = []

    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8", errors="ignore")
        if "CCB_CONFIG" in content or "cask" in content or "gask" in content:
            found.append("CLAUDE.md (configured)")
        else:
            found.append("CLAUDE.md (not configured)")
            issues.append("CLAUDE.md missing ccb rules")
    else:
        issues.append("CLAUDE.md not found")

    if settings_json.exists():
        found.append("settings.json")

    if found and not issues:
        check.pass_check(", ".join(found))
    elif found:
        check.pass_check(", ".join(found))
    else:
        check.fail_check(
            "Not configured",
            "Run: ccb install (or reinstall ccb)"
        )

    return check


def check_environment() -> DiagnosticCheck:
    """Check environment variables"""
    check = DiagnosticCheck("Environment", "ccb environment variables")

    env_vars = {
        "CCB_BACKEND_ENV": os.environ.get("CCB_BACKEND_ENV"),
        "CODEX_SESSION_ROOT": os.environ.get("CODEX_SESSION_ROOT"),
        "GEMINI_ROOT": os.environ.get("GEMINI_ROOT"),
    }

    set_vars = [k for k, v in env_vars.items() if v]

    if set_vars:
        check.pass_check(f"Set: {', '.join(set_vars)}")
    else:
        check.pass_check("Using defaults")

    return check


def check_wsl() -> Optional[DiagnosticCheck]:
    """Check WSL-specific configuration (only on WSL)"""
    # Only run on WSL
    if not os.path.exists("/proc/version"):
        return None
    try:
        version_content = Path("/proc/version").read_text().lower()
        if "microsoft" not in version_content:
            return None
    except Exception:
        return None

    check = DiagnosticCheck("WSL Configuration", "Windows Subsystem for Linux")

    # Check WSL version
    wsl_exe = shutil.which("wsl.exe")
    if not wsl_exe:
        check.pass_check("WSL detected (wsl.exe not in PATH)")
        return check

    try:
        result = subprocess.run(
            [wsl_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and ("WSL 2" in result.stdout or "WSL version: 2" in result.stdout):
            check.pass_check("WSL 2 detected")
        elif result.returncode == 0:
            check.fail_check(
                "WSL 1 detected (FIFO not supported)",
                "Upgrade to WSL 2: wsl --set-version <distro> 2"
            )
        else:
            check.pass_check("WSL detected (version unknown)")
    except Exception:
        check.pass_check("WSL detected (version unknown)")

    return check


def run_diagnostics(verbose: bool = False) -> Tuple[int, int]:
    """Run all diagnostic checks and print results"""

    checks: List[DiagnosticCheck] = []

    # Core checks
    checks.append(check_python_version())
    checks.append(check_terminal_backend())
    checks.append(check_codex_cli())
    checks.append(check_gemini_cli())

    # Configuration checks
    checks.append(check_session_files())
    checks.append(check_config_file())
    checks.append(check_claude_integration())
    checks.append(check_environment())

    # Platform-specific checks
    wsl_check = check_wsl()
    if wsl_check:
        checks.append(wsl_check)

    # Print results
    print("ccb doctor - System Diagnostics\n")
    print("=" * 50)

    passed = 0
    failed = 0

    for check in checks:
        icon = "✅" if check.passed else "❌"
        print(f"{icon} {check.name}")
        if check.message:
            print(f"   {check.message}")
        if not check.passed and check.suggestion:
            print(f"   💡 {check.suggestion}")
        passed += 1 if check.passed else 0
        failed += 0 if check.passed else 1

    print("=" * 50)
    print(f"\nSummary: {passed} passed, {failed} failed")

    if failed == 0:
        print("\n✅ All checks passed! ccb is ready to use.")
    else:
        print("\n⚠️  Some checks failed. Please review the suggestions above.")

    return passed, failed


def main() -> int:
    """Main entry point for ccb doctor"""
    import argparse

    parser = argparse.ArgumentParser(description="ccb system diagnostics")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    passed, failed = run_diagnostics(verbose=args.verbose)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
