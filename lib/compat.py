"""Windows compatibility utilities"""
import os
import sys
import subprocess
from typing import Any, Dict, Optional


def setup_windows_encoding():
    """Configure UTF-8 encoding for Windows console.

    Fixes GBK encoding issues on Windows where subprocess output
    may be decoded incorrectly.
    """
    if sys.platform == "win32":
        import io
        # Set UTF-8 encoding for stdout/stderr
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

        # Try to set console code page to UTF-8
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass


def run_subprocess(
    args: list,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    timeout: Optional[float] = None,
    **kwargs: Any
) -> subprocess.CompletedProcess:
    """Run subprocess with proper encoding handling for Windows.

    This wrapper ensures UTF-8 encoding is used on Windows to avoid
    GBK decoding errors when subprocess output contains non-ASCII characters.

    Args:
        args: Command and arguments to run
        capture_output: Capture stdout and stderr
        text: Return output as text (str) instead of bytes
        check: Raise CalledProcessError if return code is non-zero
        timeout: Timeout in seconds
        **kwargs: Additional arguments passed to subprocess.run

    Returns:
        CompletedProcess instance
    """
    # On Windows, force UTF-8 encoding to avoid GBK issues
    if sys.platform == "win32" and text:
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")

    return subprocess.run(
        args,
        capture_output=capture_output,
        text=text,
        check=check,
        timeout=timeout,
        **kwargs
    )


def safe_decode(data: bytes, fallback_encoding: str = "utf-8") -> str:
    """Safely decode bytes to string with fallback.

    Tries UTF-8 first, then falls back to specified encoding,
    and finally uses 'replace' error handling.

    Args:
        data: Bytes to decode
        fallback_encoding: Encoding to try if UTF-8 fails

    Returns:
        Decoded string
    """
    if not data:
        return ""

    # Try UTF-8 first
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Try fallback encoding (e.g., GBK for Chinese Windows)
    if fallback_encoding and fallback_encoding.lower() != "utf-8":
        try:
            return data.decode(fallback_encoding)
        except UnicodeDecodeError:
            pass

    # Last resort: decode with replacement
    return data.decode("utf-8", errors="replace")


def get_system_encoding() -> str:
    """Get the system's preferred encoding.

    Returns:
        Encoding name (e.g., 'utf-8', 'gbk', 'cp1252')
    """
    import locale

    # Try to get the preferred encoding
    encoding = locale.getpreferredencoding(False)

    # Normalize common Windows encodings
    if encoding and encoding.lower() in ("cp936", "ms936"):
        return "gbk"

    return encoding or "utf-8"
