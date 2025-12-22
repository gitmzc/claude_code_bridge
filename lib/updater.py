"""
Version checking and update utilities for ccb.
"""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path


def get_version_info(dir_path: Path) -> dict:
    """Get commit hash, date and version from install directory"""
    info = {"commit": None, "date": None, "version": None}
    ccb_file = dir_path / "ccb"
    if ccb_file.exists():
        try:
            content = ccb_file.read_text(encoding='utf-8', errors='replace')
            for line in content.split('\n')[:60]:
                line = line.strip()
                if line.startswith('VERSION') and '=' in line:
                    info["version"] = line.split('=')[1].strip().strip('"').strip("'")
                elif line.startswith('GIT_COMMIT') and '=' in line:
                    val = line.split('=')[1].strip().strip('"').strip("'")
                    if val:
                        info["commit"] = val
                elif line.startswith('GIT_DATE') and '=' in line:
                    val = line.split('=')[1].strip().strip('"').strip("'")
                    if val:
                        info["date"] = val
        except Exception:
            pass
    if shutil.which("git") and (dir_path / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(dir_path), "log", "-1", "--format=%h|%ci"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|")
            if len(parts) >= 2:
                info["commit"] = parts[0]
                info["date"] = parts[1].split()[0]
    return info


def format_version_info(info: dict) -> str:
    """Format version info for display"""
    parts = []
    if info.get("version"):
        parts.append(f"v{info['version']}")
    if info.get("commit"):
        parts.append(info["commit"])
    if info.get("date"):
        parts.append(info["date"])
    return " ".join(parts) if parts else "unknown"


def get_remote_version_info() -> dict | None:
    """Get latest version info from GitHub API"""
    import urllib.request
    import ssl

    api_url = "https://api.github.com/repos/bfly123/claude_code_bridge/commits/main"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(api_url, headers={"User-Agent": "ccb"})
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            commit = data.get("sha", "")[:7]
            date_str = data.get("commit", {}).get("committer", {}).get("date", "")
            date = date_str[:10] if date_str else None
            return {"commit": commit, "date": date}
    except Exception:
        pass

    if shutil.which("curl"):
        result = subprocess.run(
            ["curl", "-fsSL", api_url],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                commit = data.get("sha", "")[:7]
                date_str = data.get("commit", {}).get("committer", {}).get("date", "")
                date = date_str[:10] if date_str else None
                return {"commit": commit, "date": date}
            except Exception:
                pass
    return None


def update_from_git(install_dir: Path) -> tuple[bool, str]:
    """
    Update via git pull.
    Returns (success, message).
    """
    if not shutil.which("git") or not (install_dir / ".git").exists():
        return False, "Git not available or not a git repository"

    result = subprocess.run(
        ["git", "-C", str(install_dir), "pull", "--ff-only"],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    if result.returncode == 0:
        return True, result.stdout.strip() if result.stdout.strip() else "Already up to date."
    else:
        return False, f"Git pull failed: {result.stderr.strip()}"


def pick_temp_base_dir(install_dir: Path) -> Path:
    """Find a usable temporary directory."""
    candidates: list[Path] = []
    for key in ("CCB_TMPDIR", "TMPDIR", "TEMP", "TMP"):
        value = (os.environ.get(key) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    try:
        candidates.append(Path(tempfile.gettempdir()))
    except Exception:
        pass
    candidates.extend(
        [
            Path("/tmp"),
            Path("/var/tmp"),
            Path("/usr/tmp"),
            Path.home() / ".cache" / "ccb" / "tmp",
            install_dir / ".tmp",
            Path.cwd() / ".tmp",
        ]
    )

    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f".ccb_tmp_probe_{os.getpid()}_{int(time.time() * 1000)}"
            probe.write_bytes(b"1")
            probe.unlink(missing_ok=True)
            return base
        except Exception:
            continue

    raise RuntimeError(
        "❌ No usable temporary directory found.\n"
        "Fix options:\n"
        "  - Create /tmp (Linux/WSL): sudo mkdir -p /tmp && sudo chmod 1777 /tmp\n"
        "  - Or set TMPDIR/CCB_TMPDIR to a writable path (e.g. export TMPDIR=$HOME/.cache/tmp)"
    )


def update_from_tarball(install_dir: Path, repo_url: str = "https://github.com/bfly123/claude_code_bridge") -> tuple[bool, str]:
    """
    Update by downloading tarball.
    Returns (success, message).
    """
    import urllib.request

    tarball_url = f"{repo_url}/archive/refs/heads/main.tar.gz"
    try:
        tmp_base = pick_temp_base_dir(install_dir)
    except Exception as exc:
        return False, str(exc)
    tmp_dir = tmp_base / "ccb_update"

    try:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tarball_path = tmp_dir / "main.tar.gz"

        # Prefer curl/wget (better certificate handling)
        downloaded = False
        if shutil.which("curl"):
            result = subprocess.run(
                ["curl", "-fsSL", "-o", str(tarball_path), tarball_url],
                capture_output=True
            )
            downloaded = result.returncode == 0
        if not downloaded and shutil.which("wget"):
            result = subprocess.run(
                ["wget", "-q", "-O", str(tarball_path), tarball_url],
                capture_output=True
            )
            downloaded = result.returncode == 0
        if not downloaded:
            # Fallback to urllib (may have SSL issues)
            import ssl
            try:
                urllib.request.urlretrieve(tarball_url, tarball_path)
            except ssl.SSLError:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(tarball_url, context=ctx) as resp:
                    tarball_path.write_bytes(resp.read())

        def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
            dest = dest.resolve()
            for member in tar.getmembers():
                member_path = (dest / member.name).resolve()
                if not str(member_path).startswith(str(dest) + os.sep):
                    raise RuntimeError(f"Unsafe tar member path: {member.name}")
            tar.extractall(dest)

        with tarfile.open(tarball_path, "r:gz") as tar:
            _safe_extract(tar, tmp_dir)

        extracted_dir = tmp_dir / "claude_code_bridge-main"

        env = os.environ.copy()
        env["CODEX_INSTALL_PREFIX"] = str(install_dir)
        subprocess.run([str(extracted_dir / "install.sh"), "install"], check=True, env=env)

        return True, "Update successful"

    except Exception as e:
        return False, f"Update failed: {e}"

    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
