"""
Path normalization utilities for cross-platform path matching.
Handles Windows, WSL, and MSYS path variations.
"""

import os
import re
import posixpath
from pathlib import Path

# Regular expressions for path detection
WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:([/\\]|$)")
MNT_DRIVE_RE = re.compile(r"^/mnt/([A-Za-z])/(.*)$")
MSYS_DRIVE_RE = re.compile(r"^/([A-Za-z])/(.*)$")


def looks_like_windows_path(value: str) -> bool:
    """Check if a path looks like a Windows path."""
    s = value.strip()
    if not s:
        return False
    if WIN_DRIVE_RE.match(s):
        return True
    if s.startswith("\\\\") or s.startswith("//"):
        return True
    return False


def normalize_path_for_match(value: str) -> str:
    """
    Normalize a path-like string for loose matching across Windows/WSL/MSYS variations.
    This is used only for selecting a session for *current* cwd, so favor robustness.
    """
    s = (value or "").strip()
    if not s:
        return ""

    # Expand "~" early (common in shell-originated values). If expansion fails, keep original.
    if s.startswith("~"):
        try:
            s = os.path.expanduser(s)
        except Exception:
            pass

    # If the path is relative, absolutize it against current cwd for matching purposes only.
    # This reduces false negatives when upstream tools record a relative cwd.
    # NOTE: treat Windows-like absolute paths as absolute even on non-Windows hosts.
    try:
        preview = s.replace("\\", "/")
        is_abs = (
            preview.startswith("/")
            or preview.startswith("//")
            or bool(WIN_DRIVE_RE.match(preview))
            or preview.startswith("\\\\")
        )
        if not is_abs:
            s = str((Path.cwd() / Path(s)).absolute())
    except Exception:
        pass

    s = s.replace("\\", "/")

    # Map WSL drive mount to Windows-style drive path for comparison.
    m = MNT_DRIVE_RE.match(s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2)
        s = f"{drive}:/{rest}"
    else:
        # Map MSYS /c/... to c:/... (Git-Bash/MSYS2 environments on Windows).
        m = MSYS_DRIVE_RE.match(s)
        if m and ("MSYSTEM" in os.environ or os.name == "nt"):
            drive = m.group(1).lower()
            rest = m.group(2)
            s = f"{drive}:/{rest}"

    # Collapse redundant separators and dot segments using POSIX semantics (we forced "/").
    # Preserve UNC double-slash prefix.
    if s.startswith("//"):
        prefix = "//"
        rest = s[2:]
        rest = posixpath.normpath(rest)
        s = prefix + rest.lstrip("/")
    else:
        s = posixpath.normpath(s)

    # Normalize Windows drive letter casing (c:/..., not C:/...).
    if WIN_DRIVE_RE.match(s):
        s = s[0].lower() + s[1:]

    # Drop trailing slash (but keep "/" and "c:/").
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
        if WIN_DRIVE_RE.match(s) and not s.endswith("/"):
            # Ensure drive root keeps trailing slash form "c:/".
            if len(s) == 2:
                s = s + "/"

    # On Windows-like paths, compare case-insensitively to avoid drive letter/case issues.
    if looks_like_windows_path(s):
        s = s.casefold()

    return s


def work_dir_match_keys(work_dir: Path) -> set[str]:
    """
    Generate a set of normalized path keys for matching against session work directories.
    Includes variations from PWD environment variable and resolved paths.
    """
    keys: set[str] = set()
    candidates: list[str] = []
    for raw in (os.environ.get("PWD"), str(work_dir)):
        if raw:
            candidates.append(raw)
    try:
        candidates.append(str(work_dir.resolve()))
    except Exception:
        pass
    for candidate in candidates:
        normalized = normalize_path_for_match(candidate)
        if normalized:
            keys.add(normalized)
    return keys


def extract_session_work_dir_norm(session_data: dict) -> str:
    """Extract a normalized work dir marker from a session file payload."""
    if not isinstance(session_data, dict):
        return ""
    raw_norm = session_data.get("work_dir_norm")
    if isinstance(raw_norm, str) and raw_norm.strip():
        return normalize_path_for_match(raw_norm)
    raw = session_data.get("work_dir")
    if isinstance(raw, str) and raw.strip():
        return normalize_path_for_match(raw)
    return ""
