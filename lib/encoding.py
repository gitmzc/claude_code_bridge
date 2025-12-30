"""
Smart Encoding Detection - Automatically detect and decode various text encodings.

Inspired by CCCC project's _smart_decode implementation.
This helps handle cross-platform encoding issues (Windows GBK, BOM files, etc.)
"""
from __future__ import annotations
from typing import Tuple


def smart_decode(raw: bytes) -> Tuple[str, str, bool]:
    """Decode bytes to string with automatic encoding detection.

    Detection order:
    1. BOM detection (UTF-8-sig, UTF-16-LE, UTF-16-BE)
    2. UTF-8 strict mode
    3. UTF-8 with replacement (if replacement ratio <= 2% and ASCII >= 60%)
    4. UTF-16 heuristic (high NUL byte ratio)
    5. GB18030 (Chinese fallback)
    6. Latin-1 (last resort)

    Args:
        raw: Raw bytes to decode

    Returns:
        (text, encoding_name, is_lossy) tuple
        - text: Decoded string
        - encoding_name: Name of encoding used (e.g., "utf-8", "gb18030")
        - is_lossy: True if some characters were lost/replaced during decoding
    """
    if not raw:
        return "", "utf-8", False

    # 1. BOM detection
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig", errors="strict"), "utf-8-sig", False
        if raw.startswith(b"\xff\xfe"):
            return raw.decode("utf-16-le", errors="strict"), "utf-16-le", False
        if raw.startswith(b"\xfe\xff"):
            return raw.decode("utf-16-be", errors="strict"), "utf-16-be", False
    except Exception:
        pass

    # 2. UTF-8 strict mode
    try:
        return raw.decode("utf-8", errors="strict"), "utf-8", False
    except Exception:
        pass

    # 3. UTF-8 with replacement (salvage mode)
    try:
        tmp = raw.decode("utf-8", errors="replace")
        rep = tmp.count("\ufffd")
        if rep == 0:
            return tmp, "utf-8", False
        # Heuristic: prefer salvage if replacement ratio is low and ASCII share is high
        total = max(1, len(tmp))
        ascii_count = sum(1 for ch in tmp if ord(ch) < 128)
        if (rep / total) <= 0.02 and (ascii_count / total) >= 0.6:
            return tmp, "utf-8(replace)", True
    except Exception:
        pass

    # 4. UTF-16 heuristic (many NUL bytes suggest UTF-16)
    try:
        nul_count = raw.count(b"\x00")
        if nul_count > max(4, len(raw) // 8):
            # Try UTF-16-LE first (more common on Windows)
            for enc in ["utf-16-le", "utf-16-be"]:
                try:
                    return raw.decode(enc, errors="strict"), enc, False
                except Exception:
                    pass
            # Lossy fallback
            try:
                return raw.decode("utf-16-le", errors="ignore"), "utf-16-le(ignore)", True
            except Exception:
                try:
                    return raw.decode("utf-16-be", errors="ignore"), "utf-16-be(ignore)", True
                except Exception:
                    pass
    except Exception:
        pass

    # 5. GB18030 (Chinese fallback - covers GBK/GB2312)
    try:
        return raw.decode("gb18030", errors="strict"), "gb18030", False
    except Exception:
        pass

    # 6. Latin-1 (last resort - never fails)
    return raw.decode("latin1", errors="ignore"), "latin1(ignore)", True


def safe_read_file(path: str, encoding: str = None) -> Tuple[str, str]:
    """Read file with automatic encoding detection.

    Args:
        path: File path to read
        encoding: Optional encoding hint (if None, auto-detect)

    Returns:
        (content, encoding_used) tuple
    """
    with open(path, "rb") as f:
        raw = f.read()

    if encoding:
        try:
            return raw.decode(encoding), encoding
        except Exception:
            pass  # Fall through to auto-detection

    text, enc, lossy = smart_decode(raw)
    if lossy:
        import sys
        print(f"Warning: File {path} decoded with lossy encoding: {enc}", file=sys.stderr)
    return text, enc


def safe_read_bytes(raw: bytes) -> str:
    """Decode bytes with automatic encoding detection.

    Args:
        raw: Raw bytes to decode

    Returns:
        Decoded string (best effort)
    """
    text, _, _ = smart_decode(raw)
    return text
