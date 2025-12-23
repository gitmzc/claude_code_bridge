"""
Constants and version information for ccb.
"""

VERSION = "2.2"
GIT_COMMIT = ""
GIT_DATE = ""

# Default configuration
DEFAULT_CONFIG = {
    "terminal": None,  # auto-detect
    "keep_open": True,
    "warmup_timeout": 8.0,
}

# Provider names
PROVIDER_CODEX = "codex"
PROVIDER_GEMINI = "gemini"
VALID_PROVIDERS = [PROVIDER_CODEX, PROVIDER_GEMINI]
